from __future__ import annotations

import base64
import io
import os
import re
from pathlib import Path


def _client():
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        return OpenAI(timeout=60.0, max_retries=0)
    except Exception:
        return None


def _model() -> str:
    return os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_LESSON_MODEL", "gpt-4.1-mini")


def _url(image, quality=70):
    data = io.BytesIO()
    image.convert("RGB").save(data, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(data.getvalue()).decode("ascii")


def _guess_pages(topic: str, count: int) -> list[int]:
    match = re.search(r"(?:lesson|leeson|درس)\s*(\d{1,2})", topic or "", re.I)
    if match:
        number = max(1, int(match.group(1)))
        start = max(1, 5 + (number - 1) * 2)
        return list(range(start, min(count, start + 5) + 1))
    return list(range(1, min(count, 10) + 1))


def extract_scanned_pdf(path: Path, topic: str) -> str:
    client = _client()
    if client is None:
        return ""
    try:
        import fitz
        from PIL import Image

        with fitz.open(path) as pdf:
            count = len(pdf)
            pages = _guess_pages(topic, count)
            content = [{
                "type": "input_text",
                "text": (
                    f"These are scanned textbook pages. Find the requested lesson {topic!r}. "
                    "Extract only the exact lesson heading, skill, key structure, vocabulary, examples, reading text, questions, and activity instructions. "
                    "Ignore unrelated pages. Do not invent content."
                ),
            }]
            for page_number in pages:
                pix = pdf[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                content.append({"type": "input_image", "image_url": _url(image, 74), "detail": "high"})

        response = client.responses.create(
            model=_model(),
            input=[{"role": "user", "content": content}],
            max_output_tokens=2800,
            store=False,
        )
        text = str(getattr(response, "output_text", "") or "").strip()
        return f"[Scanned PDF vision extraction]\n{text}" if text else ""
    except Exception:
        return ""
