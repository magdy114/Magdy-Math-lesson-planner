from __future__ import annotations

import json
import os
import time


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
        kwargs["model"] = os.getenv("OPENAI_LESSON_MODEL", "gpt-4.1-mini")
        token_limit = _env_int("OPENAI_LESSON_MAX_TOKENS", 2200, 1400, 3200)
        try:
            current = int(kwargs.get("max_output_tokens", token_limit))
        except Exception:
            current = token_limit
        kwargs["max_output_tokens"] = min(current, token_limit)
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


def _cache_key(lesson, core) -> str:
    return json.dumps(
        [
            lesson.subject,
            lesson.class_name,
            lesson.language,
            lesson.topic,
            lesson.notes,
            core.clean_text(lesson.source_text, 1800),
        ],
        ensure_ascii=False,
    )


def _local_export_content(lesson_engine, lesson, core):
    fallback = lesson_engine.special(lesson, core)
    try:
        import lesson_density_patch

        fallback = lesson_density_patch._enrich(lesson, fallback, fallback)
    except Exception:
        pass
    fallback = dict(fallback)
    fallback["_mode"] = "fast_local_export"
    return fallback


def install(core, lesson_engine) -> None:
    """Bound AI calls and keep Word downloads independent from remote latency.

    Preview requests may use OpenAI. Word export first reuses the preview cache;
    when no preview cache exists, it immediately uses the detailed local subject
    engine. This prevents Render gateway errors while preserving AI-assisted plans
    whenever the user previews before downloading.
    """
    real_openai = getattr(lesson_engine, "OpenAI", None)
    if real_openai is not None and not getattr(lesson_engine, "_fast_openai_installed", False):
        def fast_openai(*args, **kwargs):
            kwargs["timeout"] = _env_float("OPENAI_LESSON_TIMEOUT", 12.0, 6.0, 25.0)
            kwargs["max_retries"] = 0
            return _ClientProxy(real_openai(*args, **kwargs))

        lesson_engine.OpenAI = fast_openai
        lesson_engine._fast_openai_installed = True

    if getattr(lesson_engine, "_safe_download_builder_installed", False):
        return

    original_build = lesson_engine.build_expert_content

    def safe_build(lesson, app_module):
        try:
            from flask import has_request_context, request

            is_download = has_request_context() and request.endpoint == "generate"
        except Exception:
            is_download = False

        if not is_download:
            return original_build(lesson, app_module)

        key = _cache_key(lesson, app_module)
        cached = lesson_engine.CACHE.get(key)
        if cached and time.time() - cached[0] < lesson_engine.TTL:
            return dict(cached[1])

        content = _local_export_content(lesson_engine, lesson, app_module)
        lesson_engine.CACHE[key] = (time.time(), content)
        return dict(content)

    lesson_engine.build_expert_content = safe_build
    lesson_engine._safe_download_builder_installed = True
