from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Iterable

from docx import Document


TEXT_LIMIT = 100_000


def _normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\u00a0]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:TEXT_LIMIT]


def extract_docx(path: Path) -> str:
    doc = Document(path)
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            line = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if line:
                parts.append(line)
    return _normalize("\n".join(parts))


def extract_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    with fitz.open(path) as pdf:
        max_pages = min(len(pdf), 120)
        for index in range(max_pages):
            page_text = pdf[index].get_text("text")
            if page_text.strip():
                parts.append(f"\n--- Page {index + 1} ---\n{page_text}")
            if sum(len(p) for p in parts) >= TEXT_LIMIT:
                break
    return _normalize("\n".join(parts))


def extract_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(path)
    parts: list[str] = []
    for slide_no, slide in enumerate(prs.slides, 1):
        slide_parts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_parts.append(shape.text.strip())
        if slide_parts:
            parts.append(f"Slide {slide_no}: " + " | ".join(slide_parts))
    return _normalize("\n".join(parts))


def extract_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    parts: list[str] = []
    for ws in wb.worksheets:
        parts.append(f"Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            values = [str(v).strip() for v in row if v is not None and str(v).strip()]
            if values:
                parts.append(" | ".join(values))
            if sum(len(p) for p in parts) >= TEXT_LIMIT:
                break
    return _normalize("\n".join(parts))


def extract_image(path: Path) -> str:
    # Try local OCR first, then vision through the configured AI model.
    try:
        import pytesseract
        from PIL import Image

        languages = os.getenv("TESSERACT_LANG", "eng+ara")
        text = _normalize(pytesseract.image_to_string(Image.open(path), lang=languages))
        if len(text) >= 20:
            return text
    except Exception:
        pass

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI

        mime = {
            ".png": "image/png", ".webp": "image/webp",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        }.get(path.suffix.lower(), "image/jpeg")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Extract every curriculum unit, chapter, section, and lesson title visible in this image. Preserve the original Arabic or English wording. Return one title per line with no commentary.",
                    },
                    {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"},
                ],
            }],
        )
        return _normalize(response.output_text)
    except Exception:
        return ""


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".txt", ".md", ".csv"}:
        return _normalize(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix == ".pptx":
        return extract_pptx(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return extract_image(path)
    raise ValueError("Unsupported file type")


def candidate_topics(text: str, manual_topics: str = "") -> list[str]:
    source = "\n".join([manual_topics or "", text or ""])
    raw_lines = re.split(r"[\n;•]+", source)
    candidates: list[str] = []
    seen: set[str] = set()

    noise_patterns = (
        "copyright", "all rights reserved", "page ", "contents", "table of contents",
        "academic year", "emirates private school", "www.", "http://", "https://",
    )
    for raw in raw_lines:
        line = re.sub(r"\s+", " ", raw).strip(" -–—|:.,\t")
        if not line or len(line) < 3 or len(line) > 140:
            continue
        lower = line.lower()
        if any(noise in lower for noise in noise_patterns):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        words = line.split()
        if len(words) > 18:
            continue
        # Strong candidates: numbered headings, unit/chapter/lesson names, or short lines.
        heading_like = bool(re.match(r"^(unit|chapter|lesson|section|الوحدة|الفصل|الدرس)\b", lower))
        numbered = bool(re.match(r"^\d+(?:\.\d+)*\s+", line))
        if not (heading_like or numbered or len(words) <= 11):
            continue
        key = re.sub(r"\W+", "", lower)
        if key and key not in seen:
            seen.add(key)
            candidates.append(line)
        if len(candidates) >= 120:
            break
    return candidates
