from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None


CACHE_VERSION = "lesson-docx-v3"
_CACHE_CLEAN_LOCK = threading.Lock()
_LIBRARY_LOCK = threading.RLock()
_USAGE_LOCK = threading.RLock()
_LOCAL_KEY_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_KEY_LOCKS_GUARD = threading.Lock()
_LAST_CLEANUP = 0.0


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _normal(value: str, limit: int = 10000) -> str:
    text = " ".join(str(value or "").replace("\r", "\n").split())
    return text[:limit]


def _lesson_signature(lesson, template_path: Path) -> str:
    try:
        template_stamp = int(template_path.stat().st_mtime_ns)
    except Exception:
        template_stamp = 0
    payload = {
        "v": CACHE_VERSION,
        "template": template_stamp,
        "teacher": _normal(lesson.teacher, 250),
        "subject": _normal(lesson.subject, 250),
        "class": _normal(lesson.class_name, 250),
        "periods": _normal(lesson.periods, 120),
        "language": lesson.language,
        "topic": _normal(lesson.topic, 500),
        "date": _normal(lesson.date, 80),
        "notes": _normal(lesson.notes, 2500),
        "source": _normal(lesson.source_text, 12000),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _thread_lock(key: str) -> threading.Lock:
    with _LOCAL_KEY_LOCKS_GUARD:
        lock = _LOCAL_KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCAL_KEY_LOCKS[key] = lock
        return lock


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    thread_lock = _thread_lock(path.name)
    with thread_lock:
        handle = path.open("a+b")
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            handle.close()


def _valid_cache(path: Path, ttl_seconds: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 5000 and time.time() - path.stat().st_mtime < ttl_seconds
    except OSError:
        return False


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _cleanup_cache(cache_dir: Path, ttl_seconds: int, max_files: int) -> None:
    global _LAST_CLEANUP
    now = time.time()
    if now - _LAST_CLEANUP < 900:
        return
    if not _CACHE_CLEAN_LOCK.acquire(blocking=False):
        return
    try:
        _LAST_CLEANUP = now
        files = []
        for path in cache_dir.glob("*.docx"):
            try:
                stat = path.stat()
                if now - stat.st_mtime > ttl_seconds:
                    path.unlink(missing_ok=True)
                else:
                    files.append((stat.st_mtime, path))
            except OSError:
                continue
        files.sort(reverse=True)
        for _, path in files[max_files:]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for path in cache_dir.glob("*.lock"):
            try:
                if now - path.stat().st_mtime > 86400:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        _CACHE_CLEAN_LOCK.release()


def install(core) -> None:
    if getattr(core, "_teacher_load_patch_installed", False):
        return

    cache_dir = core.BASE_DIR / "runtime_cache" / "lesson_docx"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ttl_seconds = _env_int("LESSON_CACHE_HOURS", 168, 1, 720) * 3600
    max_files = _env_int("LESSON_CACHE_MAX_FILES", 400, 50, 2000)
    max_concurrent = _env_int("LESSON_MAX_CONCURRENT", 2, 1, 4)
    wait_seconds = _env_int("LESSON_QUEUE_WAIT_SECONDS", 75, 15, 150)
    generation_slots = threading.BoundedSemaphore(max_concurrent)

    original_add_to_library = core.add_to_library
    original_check_usage_limit = core.check_usage_limit

    def safe_add_to_library(record):
        with _LIBRARY_LOCK:
            return original_add_to_library(record)

    def safe_check_usage_limit(user_key):
        with _USAGE_LOCK:
            return original_check_usage_limit(user_key)

    core.add_to_library = safe_add_to_library
    core.check_usage_limit = safe_check_usage_limit

    def get_or_create_docx(lesson):
        key = _lesson_signature(lesson, core.TEMPLATE_PATH)
        cache_path = cache_dir / f"{key}.docx"
        lock_path = cache_dir / f"{key}.lock"

        if _valid_cache(cache_path, ttl_seconds):
            return cache_path.read_bytes(), True

        with _file_lock(lock_path):
            if _valid_cache(cache_path, ttl_seconds):
                return cache_path.read_bytes(), True

            acquired = generation_slots.acquire(timeout=wait_seconds)
            if not acquired:
                raise RuntimeError(
                    "يوجد ضغط مرتفع حاليًا. انتظر قليلًا ثم أعد المحاولة؛ لم يتم فقد بيانات الدرس."
                )
            try:
                started = time.monotonic()
                data = core.generate_docx(lesson)
                _atomic_write(cache_path, data)
                core.logger.info(
                    "Lesson DOCX generated: key=%s topic=%s elapsed=%.2fs",
                    key[:10], lesson.topic, time.monotonic() - started,
                )
                return data, False
            finally:
                generation_slots.release()

    def generate_for_teachers():
        _cleanup_cache(cache_dir, ttl_seconds, max_files)
        lessons, errors = core.parse_lessons_from_request()
        if errors:
            return core.render_template(
                "index.html", error=" | ".join(errors), status=core.status_payload()
            ), 400

        user_key = lessons[0].teacher or core.request.remote_addr or "anonymous"
        for _lesson in lessons:
            ok_limit, limit_msg = core.check_usage_limit(user_key)
            if not ok_limit:
                return core.render_template(
                    "index.html", error=limit_msg, status=core.status_payload()
                ), 429

        generated = []
        cache_hits = 0
        try:
            for lesson in lessons:
                docx_bytes, cache_hit = get_or_create_docx(lesson)
                cache_hits += int(cache_hit)
                stored_name = core.store_docx_file(lesson, docx_bytes)
                generated.append((stored_name, docx_bytes))
        except Exception as exc:
            core.logger.exception("Error while generating cached DOCX")
            return core.render_template(
                "index.html",
                error=f"تعذر إنشاء ملف Word. {exc}",
                status=core.status_payload(),
            ), 503

        if len(generated) == 1:
            filename, docx_bytes = generated[0]
            response = core.send_file(
                io.BytesIO(docx_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name=filename,
            )
            response.headers["X-Lesson-Cache"] = "HIT" if cache_hits else "MISS"
            response.headers["X-Lesson-Concurrency"] = str(max_concurrent)
            return response

        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for filename, docx_bytes in generated:
                archive.writestr(filename, docx_bytes)
        zip_bytes.seek(0)
        zip_name = f"Lesson_Plans_Batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        response = core.send_file(
            zip_bytes,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )
        response.headers["X-Lesson-Cache-Hits"] = str(cache_hits)
        response.headers["X-Lesson-Concurrency"] = str(max_concurrent)
        return response

    core.generate = generate_for_teachers
    core.app.view_functions["generate"] = generate_for_teachers
    core._teacher_load_patch_installed = True
