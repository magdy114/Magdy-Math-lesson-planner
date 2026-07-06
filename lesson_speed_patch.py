from __future__ import annotations

import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


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


class _ResponsesProxy:
    def __init__(self, responses):
        self._responses = responses

    def parse(self, *args, **kwargs):
        # Use a dedicated lesson model instead of inheriting a potentially slow
        # general-purpose model from OPENAI_MODEL.
        kwargs["model"] = os.getenv("OPENAI_LESSON_MODEL", "gpt-4.1-mini")
        token_limit = _env_int("OPENAI_LESSON_MAX_TOKENS", 2600, 1600, 3800)
        current = kwargs.get("max_output_tokens", token_limit)
        try:
            kwargs["max_output_tokens"] = min(int(current), token_limit)
        except Exception:
            kwargs["max_output_tokens"] = token_limit
        kwargs["store"] = False
        return self._responses.parse(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._responses, name)


class _ClientProxy:
    def __init__(self, client):
        self._client = client
        self.responses = _ResponsesProxy(client.responses)

    def __getattr__(self, name):
        return getattr(self._client, name)


def _install_fast_openai(lesson_engine) -> None:
    real_openai = getattr(lesson_engine, "OpenAI", None)
    if real_openai is None or getattr(lesson_engine, "_fast_openai_installed", False):
        return

    def fast_openai(*args, **kwargs):
        kwargs["timeout"] = _env_float("OPENAI_LESSON_TIMEOUT", 18.0, 8.0, 35.0)
        kwargs["max_retries"] = 0
        return _ClientProxy(real_openai(*args, **kwargs))

    lesson_engine.OpenAI = fast_openai
    lesson_engine._fast_openai_installed = True


def _install_parallel_export(core) -> None:
    if getattr(core, "_parallel_lesson_export_installed", False):
        return

    def generate_fast():
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

        try:
            documents: list[bytes | None] = [None] * len(lessons)
            workers = min(
                len(lessons),
                _env_int("LESSON_BATCH_WORKERS", 3, 1, 5),
            )

            if len(lessons) == 1:
                documents[0] = core.generate_docx(lessons[0])
            else:
                # OpenAI calls are network-bound. Running a small bounded group in
                # parallel prevents five lessons from waiting one after another.
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lesson-plan") as executor:
                    futures = {
                        executor.submit(core.generate_docx, lesson): index
                        for index, lesson in enumerate(lessons)
                    }
                    for future in as_completed(futures):
                        index = futures[future]
                        documents[index] = future.result()

            generated: list[tuple[str, bytes]] = []
            # Library writes remain sequential to avoid concurrent JSON updates.
            for lesson, docx_bytes in zip(lessons, documents):
                if docx_bytes is None:
                    raise RuntimeError("تعذر إنشاء أحد ملفات التحضير.")
                stored_name = core.store_docx_file(lesson, docx_bytes)
                generated.append((stored_name, docx_bytes))

        except Exception as exc:
            core.logger.exception("Error while generating DOCX batch")
            return core.render_template(
                "index.html",
                error=(
                    "حدث خطأ أثناء إنشاء الملف، لكن التطبيق لم يغلق. "
                    f"التفاصيل محفوظة في logs/error_log.txt\n{exc}"
                ),
                status=core.status_payload(),
            ), 500

        if len(generated) == 1:
            filename, docx_bytes = generated[0]
            return core.send_file(
                io.BytesIO(docx_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name=filename,
            )

        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename, docx_bytes in generated:
                archive.writestr(filename, docx_bytes)
        zip_bytes.seek(0)
        zip_name = f"Lesson_Plans_Batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return core.send_file(
            zip_bytes,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    core.generate = generate_fast
    core.app.view_functions["generate"] = generate_fast
    core._parallel_lesson_export_installed = True


def install(core, lesson_engine) -> None:
    _install_fast_openai(lesson_engine)
    _install_parallel_export(core)
