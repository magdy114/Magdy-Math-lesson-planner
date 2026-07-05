from __future__ import annotations

import base64
import io
import os
import re
import time
from pathlib import Path

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".jfif", ".bmp", ".gif",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}


def _clean_line(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:180]


def _fast_pdf(path: Path) -> str:
    import fitz

    output: list[str] = []
    seen: set[str] = set()
    deadline = time.monotonic() + 8.0

    def add(value: str) -> None:
        value = _clean_line(value)
        key = re.sub(r"[^\w\u0600-\u06ff]+", "", value.casefold())
        if not value or not key or key in seen:
            return
        if len(value.split()) > 16:
            return
        seen.add(key)
        output.append(value)

    with fitz.open(path) as pdf:
        try:
            for item in (pdf.get_toc(simple=True) or [])[:120]:
                if len(item) >= 2:
                    add(str(item[1]))
        except Exception:
            pass

        if len(output) < 6:
            for page_no in range(min(len(pdf), 14)):
                if time.monotonic() >= deadline or len(output) >= 80:
                    break
                try:
                    text = pdf[page_no].get_text("text", sort=True) or ""
                except Exception:
                    continue
                kept = 0
                for raw in text.splitlines():
                    line = _clean_line(raw)
                    if not line or len(line.split()) > 13 or len(line) > 110:
                        continue
                    lower = line.casefold()
                    if any(term in lower for term in (
                        "copyright", "isbn", "publisher", "mcgraw", "pearson", "www.", "http",
                        "example", "exercise", "solution", "حقوق الطبع", "الناشر", "مثال", "تمرين", "الحل",
                    )):
                        continue
                    if re.search(r"[.!?؟؛]$", line):
                        continue
                    add(line)
                    kept += 1
                    if kept >= 10:
                        break

    return "\n".join(f"[HEADING] {item}" for item in output)


def _image_as_jpeg_data_url(path: Path) -> str:
    from PIL import Image, ImageOps

    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except Exception:
        pass

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if getattr(image, "is_animated", False):
            image.seek(0)
        if image.mode not in {"RGB", "L"}:
            background = Image.new("RGB", image.size, "white")
            if image.mode == "RGBA":
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image.convert("RGB"))
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((2200, 2200))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _image_with_openai(path: Path) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=22.0, max_retries=0)
        response = client.responses.create(
            model=os.getenv("CURRICULUM_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Read this curriculum contents-page image. Return only genuine unit, chapter, "
                            "section, and lesson titles, one title per line, in their original language. "
                            "Remove page numbers, lesson codes, publisher text, copyright text, examples, "
                            "questions, equations, and commentary. Do not invent any title."
                        ),
                    },
                    {"type": "input_image", "image_url": _image_as_jpeg_data_url(path)},
                ],
            }],
            max_output_tokens=1800,
            store=False,
        )
        return str(getattr(response, "output_text", "") or "").strip()
    except Exception:
        return ""


def _image_with_local_ocr(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            pass

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if getattr(image, "is_animated", False):
                image.seek(0)
            image.thumbnail((2200, 2200))
            return pytesseract.image_to_string(
                image.convert("RGB"),
                lang=os.getenv("TESSERACT_LANG", "eng+ara"),
                timeout=10,
            ).strip()
    except Exception:
        return ""


def _fast_image(path: Path) -> str:
    text = _image_with_openai(path)
    if not text:
        text = _image_with_local_ocr(path)
    return text


def install(core) -> None:
    original_extract = core.extract_curriculum_text
    original_secure_filename = core.secure_filename

    def safe_secure_filename(filename: str) -> str:
        """Preserve the real extension when the original basename is Arabic/non-Latin.

        Werkzeug may turn فهرس.png into just 'png', which removes the dot and makes
        the saved upload look extensionless. The extractor then reports an unsupported
        file type even though the uploaded file is a valid PNG.
        """
        original = str(filename or "")
        extension = Path(original).suffix.lower().lstrip(".")
        safe = original_secure_filename(original)
        safe_extension = Path(safe).suffix.lower().lstrip(".") if safe else ""
        if extension and safe_extension != extension:
            safe_stem = original_secure_filename(Path(original).stem) or "curriculum"
            safe = f"{safe_stem}.{extension}"
        return safe or (f"curriculum.{extension}" if extension else "curriculum")

    def fast_extract(path: Path) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            return _fast_pdf(Path(path))
        if suffix in IMAGE_EXTENSIONS:
            return _fast_image(Path(path))
        return original_extract(path)

    def local_refine(meta, source_text, candidates, language):
        from curriculum_ai import clean_topics
        return clean_topics(candidates)

    core.CURRICULUM_ALLOWED_EXTENSIONS.update(ext.lstrip(".") for ext in IMAGE_EXTENSIONS)
    core.secure_filename = safe_secure_filename
    core.extract_curriculum_text = fast_extract
    core.refine_topics = local_refine
