from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl  # Linux/Render process-safe file locks
except Exception:  # pragma: no cover - Windows development fallback
    fcntl = None

try:
    from diskcache import Cache
except Exception:  # pragma: no cover
    Cache = None


_THREAD_FILE_LOCK = threading.RLock()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


@contextmanager
def _file_lock(path: Path):
    """Serialize JSON read/modify/write operations across Gunicorn workers."""
    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    with _THREAD_FILE_LOCK:
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


def _read_json_unlocked(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_unlocked(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    )
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _fast_local_lesson(lesson_engine, lesson, core, mode: str) -> dict[str, Any]:
    content = lesson_engine.special(lesson, core)
    try:
        import lesson_density_patch

        content = lesson_density_patch._enrich(lesson, content, content)
    except Exception:
        pass
    content = dict(content)
    content["_mode"] = mode
    return content


def _fast_local_topics(meta: dict, candidates: list[str], language: str) -> list[str]:
    try:
        import curriculum_ai

        base = curriculum_ai.clean_topics(candidates)
        localized = curriculum_ai._localize(base, language)
        return localized or curriculum_ai._defaults(meta, language)
    except Exception:
        return [str(x).strip() for x in candidates if str(x).strip()][:60]


def _cleanup_folder(folder: Path, max_age_hours: int) -> None:
    if not folder.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    for path in folder.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except Exception:
            continue


def install(core, lesson_engine) -> None:
    """Install shared caching, bounded AI concurrency and process-safe storage.

    This patch is intentionally optional and preserves the existing local fallback.
    It makes one Render instance useful to several teachers without allowing a burst
    of OpenAI calls or simultaneous JSON writes to block/corrupt the application.
    """
    if getattr(core, "_scalable_runtime_installed", False):
        return

    cache_dir = Path(os.getenv("RUNTIME_CACHE_DIR", str(core.BASE_DIR / ".runtime_cache")))
    cache_size_mb = _env_int("RUNTIME_CACHE_SIZE_MB", 256, 32, 2048)
    cache = Cache(str(cache_dir), size_limit=cache_size_mb * 1024 * 1024) if Cache else None

    lesson_ttl = _env_int("LESSON_SHARED_CACHE_TTL", 21600, 60, 86400)
    extraction_ttl = _env_int("EXTRACTION_CACHE_TTL", 86400, 300, 604800)
    topic_ttl = _env_int("CURRICULUM_TOPIC_CACHE_TTL", 43200, 300, 86400)
    ai_parallel = _env_int("AI_MAX_CONCURRENCY_PER_WORKER", 2, 1, 8)
    ai_wait = _env_float("AI_QUEUE_WAIT_SECONDS", 1.5, 0.0, 10.0)
    ai_gate = threading.BoundedSemaphore(ai_parallel)

    # Flask/runtime tuning.
    core.app.config["SEND_FILE_MAX_AGE_DEFAULT"] = _env_int(
        "STATIC_CACHE_SECONDS", 86400, 0, 604800
    )
    core.app.config["MAX_CONTENT_LENGTH"] = _env_int(
        "MAX_UPLOAD_MB", 35, 5, 100
    ) * 1024 * 1024
    core.app.config["JSON_AS_ASCII"] = False

    # Atomic JSON helpers. These replace the unsafe direct write_text implementation.
    def safe_load_json(path: Path, default: Any) -> Any:
        path = Path(path)
        with _file_lock(path):
            return _read_json_unlocked(path, default)

    def safe_save_json(path: Path, data: Any) -> None:
        path = Path(path)
        with _file_lock(path):
            _write_json_unlocked(path, data)

    def safe_check_usage_limit(user_key: str):
        path = Path(core.USAGE_PATH)
        with _file_lock(path):
            today = datetime.now().strftime("%Y-%m-%d")
            data = _read_json_unlocked(path, {})
            if data.get("date") != today:
                data = {"date": today, "total": 0, "users": {}}
            total_limit = core.env_int("DAILY_TOTAL_LIMIT", 300)
            user_limit = core.env_int("DAILY_USER_LIMIT", 25)
            clean_key = core.safe_filename(user_key or "anonymous", "anonymous")[:80]
            total = int(data.get("total", 0))
            user_count = int(data.get("users", {}).get(clean_key, 0))
            if total >= total_limit:
                return False, "تم الوصول للحد اليومي العام. حاول غدًا أو زد الحد من إعدادات Render."
            if user_count >= user_limit:
                return False, "تم الوصول للحد اليومي لهذا المستخدم."
            data["total"] = total + 1
            data.setdefault("users", {})[clean_key] = user_count + 1
            _write_json_unlocked(path, data)
            return True, ""

    def safe_save_library(items):
        path = Path(core.META_PATH)
        with _file_lock(path):
            _write_json_unlocked(path, list(items)[:500])

    def safe_add_to_library(record):
        path = Path(core.META_PATH)
        with _file_lock(path):
            items = _read_json_unlocked(path, [])
            filename = record.get("filename")
            if filename:
                items = [item for item in items if item.get("filename") != filename]
            items.insert(0, record)
            _write_json_unlocked(path, items[:500])

    core.load_json = safe_load_json
    core.save_json = safe_save_json
    core.check_usage_limit = safe_check_usage_limit
    core.save_library = safe_save_library
    core.add_to_library = safe_add_to_library

    # Cache lesson content across threads and Gunicorn worker processes.
    original_lesson_builder = lesson_engine.build_expert_content

    def shared_lesson_builder(lesson, app_module):
        template_version = 0
        try:
            template_version = int(Path(app_module.TEMPLATE_PATH).stat().st_mtime)
        except Exception:
            pass
        key = "lesson:" + _stable_hash(
            {
                "v": 3,
                "template": template_version,
                "teacher": lesson.teacher,
                "subject": lesson.subject,
                "class": lesson.class_name,
                "periods": lesson.periods,
                "language": lesson.language,
                "topic": lesson.topic,
                "notes": lesson.notes,
                "source": app_module.clean_text(lesson.source_text, 6000),
            }
        )
        if cache is not None:
            cached = cache.get(key, default=None)
            if isinstance(cached, dict):
                result = dict(cached)
                result["_cache"] = "shared"
                return result

        try:
            from flask import has_request_context, request

            endpoint = request.endpoint if has_request_context() else ""
        except Exception:
            endpoint = ""

        # The existing speed patch already makes /generate local and immediate.
        needs_ai_slot = endpoint != "generate" and bool(os.getenv("OPENAI_API_KEY"))
        acquired = True
        if needs_ai_slot:
            acquired = ai_gate.acquire(timeout=ai_wait)
        if not acquired:
            return _fast_local_lesson(
                lesson_engine, lesson, app_module, "fast_busy_fallback"
            )

        try:
            content = dict(original_lesson_builder(lesson, app_module))
        except Exception:
            app_module.logger.exception("Shared lesson generation failed; using local engine")
            content = _fast_local_lesson(
                lesson_engine, lesson, app_module, "fast_error_fallback"
            )
        finally:
            if needs_ai_slot and acquired:
                ai_gate.release()

        if cache is not None and isinstance(content, dict):
            try:
                cache.set(key, dict(content), expire=lesson_ttl)
            except Exception:
                pass
        return dict(content)

    lesson_engine.build_expert_content = shared_lesson_builder

    # Cache curriculum title refinement and use local refinement during traffic bursts.
    original_refine_topics = core.refine_topics

    def shared_refine_topics(meta, source_text, candidates, language):
        key = "topics:" + _stable_hash(
            {
                "v": 2,
                "meta": meta,
                "language": language,
                "candidates": list(candidates)[:100],
                "source_hash": hashlib.sha256(
                    str(source_text or "").encode("utf-8", errors="ignore")
                ).hexdigest(),
            }
        )
        if cache is not None:
            cached = cache.get(key, default=None)
            if isinstance(cached, list) and cached:
                return list(cached)

        needs_ai_slot = bool(os.getenv("OPENAI_API_KEY"))
        acquired = ai_gate.acquire(timeout=ai_wait) if needs_ai_slot else True
        if acquired:
            try:
                result = original_refine_topics(meta, source_text, candidates, language)
            except Exception:
                core.logger.exception("Curriculum refinement failed; using local titles")
                result = _fast_local_topics(meta, list(candidates), language)
            finally:
                if needs_ai_slot:
                    ai_gate.release()
        else:
            result = _fast_local_topics(meta, list(candidates), language)

        result = list(result or [])
        if cache is not None and result:
            try:
                cache.set(key, result, expire=topic_ttl)
            except Exception:
                pass
        return result

    core.refine_topics = shared_refine_topics

    # Cache text extraction for repeated books/templates even when uploaded under a new name.
    def wrap_extractor(name: str, original: Callable):
        def cached_extractor(path, *args, **kwargs):
            path_obj = Path(path)
            try:
                fingerprint = _file_fingerprint(path_obj)
                key = f"extract:{name}:{fingerprint}:{args}:{sorted(kwargs.items())}"
                if cache is not None:
                    cached = cache.get(key, default=None)
                    if isinstance(cached, str):
                        return cached
                result = original(path_obj, *args, **kwargs)
                if cache is not None and isinstance(result, str):
                    cache.set(key, result, expire=extraction_ttl)
                return result
            except Exception:
                return original(path_obj, *args, **kwargs)

        return cached_extractor

    for extractor_name in (
        "extract_docx_text",
        "extract_pdf_text",
        "extract_pptx_text",
        "extract_txt_text",
        "extract_curriculum_text",
    ):
        original = getattr(core, extractor_name, None)
        if callable(original):
            setattr(core, extractor_name, wrap_extractor(extractor_name, original))

    # Lightweight request timing plus periodic cleanup of temporary files.
    from flask import g

    @core.app.before_request
    def scalable_runtime_before_request():
        g._runtime_started_at = time.perf_counter()
        if cache is None:
            return
        try:
            if cache.add("maintenance:cleanup", time.time(), expire=3600):
                _cleanup_folder(
                    Path(core.UPLOAD_DIR),
                    _env_int("UPLOAD_RETENTION_HOURS", 24, 1, 720),
                )
                _cleanup_folder(
                    Path(core.CURRICULUM_UPLOAD_DIR),
                    _env_int("UPLOAD_RETENTION_HOURS", 24, 1, 720),
                )
                retention = _env_int("GENERATED_RETENTION_HOURS", 168, 24, 2160)
                _cleanup_folder(Path(core.CURRICULUM_JOB_DIR), retention)
                _cleanup_folder(Path(core.CURRICULUM_EXPORT_DIR), retention)
        except Exception:
            core.logger.exception("Temporary-file cleanup failed")

    @core.app.after_request
    def scalable_runtime_after_request(response):
        try:
            started = getattr(g, "_runtime_started_at", None)
            if started is not None:
                response.headers["Server-Timing"] = (
                    f'app;dur={(time.perf_counter() - started) * 1000:.1f}'
                )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            if response.mimetype == "text/html":
                response.headers["Cache-Control"] = "no-store"
        except Exception:
            pass
        return response

    core.runtime_cache = cache
    core._scalable_runtime_installed = True
