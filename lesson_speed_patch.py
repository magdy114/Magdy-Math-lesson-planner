from __future__ import annotations

import os


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


def install(core, lesson_engine) -> None:
    """Keep OpenAI calls bounded without parallelising full DOCX generation.

    Running several lesson exports concurrently can exhaust the memory available
    on a small Render instance and cause a 502. The original Flask export route
    remains intact; lessons are generated safely in sequence.
    """
    real_openai = getattr(lesson_engine, "OpenAI", None)
    if real_openai is None or getattr(lesson_engine, "_fast_openai_installed", False):
        return

    def fast_openai(*args, **kwargs):
        kwargs["timeout"] = _env_float("OPENAI_LESSON_TIMEOUT", 15.0, 8.0, 30.0)
        kwargs["max_retries"] = 0
        return _ClientProxy(real_openai(*args, **kwargs))

    lesson_engine.OpenAI = fast_openai
    lesson_engine._fast_openai_installed = True
