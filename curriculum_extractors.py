from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from docx import Document


TEXT_LIMIT = 100_000


NOISE_TERMS = (
    "copyright", "all rights reserved", "rights reserved", "permission", "permissions",
    "reproduced", "reproduction", "publisher", "publishing", "isbn", "mcgraw", "pearson",
    "sourced from", "source:", "education, llc", "trademark", "printed in", "edition",
    "www.", "http://", "https://", "chapter ©", "©", "®", "™",
    "حقوق الطبع", "جميع الحقوق محفوظة", "الناشر", "الطبعة", "ردمك", "حقوق النشر",
    "تم النشر", "لا يجوز", "إعادة إنتاج", "المؤلف", "المراجع", "المصدر",
)

HEADING_WORDS = (
    "unit", "chapter", "lesson", "section", "module", "topic", "strand", "domain",
    "الوحدة", "الفصل", "الدرس", "الموضوع", "المحور", "المجال", "الباب",
)

BODY_HINTS = (
    "for differentiation", "differentiation", "answer the following", "example", "exercise",
    "practice", "find the", "calculate", "suppose", "if the", "where the", "is defined",
    "حل المثال", "أوجد", "احسب", "إذا كان", "حيث إن", "يوضح الشكل", "تدرب", "مثال",
    "نشاط", "ناقش", "فسر", "علل", "اختر الإجابة", "اكتب", "استخدم الشكل",
)


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
            style_name = (p.style.name or "").lower() if p.style else ""
            prefix = "[HEADING] " if "heading" in style_name or "title" in style_name else ""
            parts.append(prefix + p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            line = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if line:
                parts.append(line)
    return _normalize("\n".join(parts))


def _pdf_page_lines(page) -> list[tuple[str, float, float]]:
    """Return text lines with their maximum and median font sizes."""
    output: list[tuple[str, float, float]] = []
    data = page.get_text("dict")
    page_sizes: list[float] = []
    raw_lines: list[tuple[str, float]] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            sizes = [float(span.get("size", 0) or 0) for span in spans if span.get("text", "").strip()]
            max_size = max(sizes) if sizes else 0.0
            page_sizes.extend(sizes)
            raw_lines.append((text, max_size))
    if not page_sizes:
        return []
    sorted_sizes = sorted(page_sizes)
    median = sorted_sizes[len(sorted_sizes) // 2]
    for text, max_size in raw_lines:
        output.append((text, max_size, median))
    return output


def extract_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    current_len = 0
    with fitz.open(path) as pdf:
        max_pages = min(len(pdf), 120)
        for index in range(max_pages):
            page = pdf[index]
            parts.append(f"\n--- Page {index + 1} ---")
            current_len += 20
            for line, max_size, median_size in _pdf_page_lines(page):
                clean = re.sub(r"\s+", " ", line).strip()
                if not clean:
                    continue
                # Mark likely headings, while retaining regular text for AI context.
                heading = (
                    len(clean) <= 140
                    and max_size >= max(11.0, median_size * 1.22)
                    and len(clean.split()) <= 18
                )
                tagged = f"[HEADING] {clean}" if heading else clean
                parts.append(tagged)
                current_len += len(tagged)
                if current_len >= TEXT_LIMIT:
                    break
            if current_len >= TEXT_LIMIT:
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
                text = shape.text.strip()
                prefix = "[HEADING] " if getattr(shape, "shape_type", None) is not None and len(text.split()) <= 16 else ""
                slide_parts.append(prefix + text)
        if slide_parts:
            parts.append(f"Slide {slide_no}: " + " | ".join(slide_parts))
    return _normalize("\n".join(parts))


def extract_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    parts: list[str] = []
    total = 0
    for ws in wb.worksheets:
        parts.append(f"[HEADING] Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            values = [str(v).strip() for v in row if v is not None and str(v).strip()]
            if values:
                line = " | ".join(values)
                parts.append(line)
                total += len(line)
            if total >= TEXT_LIMIT:
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
                        "text": (
                            "Extract only curriculum unit, chapter, section, and lesson titles visible in this image. "
                            "Ignore publisher information, copyright, ISBN, page numbers, examples, exercise questions, "
                            "explanatory sentences, and teacher notes. Preserve the original Arabic or English wording. "
                            "Return one concise curriculum title per line with no commentary."
                        ),
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


def _strip_page_artifacts(line: str) -> str:
    line = re.sub(r"^\[HEADING\]\s*", "", line, flags=re.I)
    line = re.sub(r"^---\s*Page\s+\d+\s*---$", "", line, flags=re.I)
    line = re.sub(r"\.{2,}\s*\d+\s*$", "", line)
    line = re.sub(r"\s+\d{1,4}\s*$", "", line) if "..." in line else line
    line = re.sub(r"\s+", " ", line).strip(" -–—|:.,;\t")
    return line


def _is_noise(line: str) -> bool:
    lower = line.casefold()
    if any(term in lower for term in NOISE_TERMS):
        return True
    if re.search(r"\b(?:19|20)\d{2}\b", line) and not re.match(r"^\d+(?:\.\d+)+\s+", line):
        return True
    if re.search(r"\b(?:ISBN|DOI)\b", line, re.I):
        return True
    if re.search(r"\b\d+(?:st|nd|rd|th)?\s*(?:edition|ed\.?|e)\s*$", line, re.I):
        return True
    if "@" in line or re.search(r"\.(?:com|org|net|edu)\b", lower):
        return True
    if re.fullmatch(r"[\d\W_]+", line):
        return True
    return False


def _looks_like_body(line: str) -> bool:
    lower = line.casefold()
    words = line.split()
    if any(hint in lower for hint in BODY_HINTS):
        return True
    # Long prose, especially with sentence punctuation, is not a curriculum title.
    if len(words) > 14:
        return True
    if len(words) >= 8 and re.search(r"[.!?؟؛:]$", line):
        return True
    if len(line) > 110:
        return True
    # Reject equation/exercise fragments that carry many digits or operators.
    digit_count = sum(ch.isdigit() for ch in line)
    operator_count = sum(ch in "+=<>[]{}" for ch in line)
    if digit_count >= 5 or operator_count >= 3:
        return True
    return False


def _is_strong_topic(raw_line: str, cleaned: str) -> bool:
    lower = cleaned.casefold()
    tagged_heading = raw_line.lstrip().lower().startswith("[heading]")
    heading_word = any(re.match(rf"^{re.escape(word)}\b", lower) for word in HEADING_WORDS)
    hierarchical_number = bool(re.match(r"^\d+(?:\.\d+){1,3}\s+\S", cleaned))
    simple_lesson_number = bool(re.match(r"^(?:lesson|الدرس)\s*\d+\b", lower))
    toc_dots = bool(re.search(r"\.{2,}\s*\d+\s*$", raw_line))
    return tagged_heading or heading_word or hierarchical_number or simple_lesson_number or toc_dots


def _dedupe_key(line: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", "", line.casefold())


def _manual_topic_lines(manual_topics: str) -> list[str]:
    lines = re.split(r"[\n;•]+", manual_topics or "")
    output: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = _strip_page_artifacts(raw)
        if not line or len(line) < 3 or len(line) > 140 or _is_noise(line):
            continue
        key = _dedupe_key(line)
        if key and key not in seen:
            seen.add(key)
            output.append(line)
    return output


def candidate_topics(text: str, manual_topics: str = "") -> list[str]:
    """Return clean curriculum headings, prioritising manually supplied topics.

    Whole textbooks contain legal notices, examples, body paragraphs, and exercises. This
    function deliberately accepts only heading-like source lines, while manual entries are
    treated as authoritative.
    """
    manual = _manual_topic_lines(manual_topics)
    candidates: list[str] = list(manual)
    seen: set[str] = {_dedupe_key(x) for x in manual}

    raw_lines = re.split(r"[\n•]+", text or "")
    strong_lines: list[str] = []
    secondary_lines: list[str] = []

    for raw in raw_lines:
        cleaned = _strip_page_artifacts(raw)
        if not cleaned or len(cleaned) < 3 or len(cleaned) > 140:
            continue
        if _is_noise(cleaned) or _looks_like_body(cleaned):
            continue
        words = cleaned.split()
        strong = _is_strong_topic(raw, cleaned)
        # Secondary candidates are intentionally strict: short title-style phrases only.
        secondary = (
            len(words) <= 7
            and not re.search(r"[.!?؟؛]", cleaned)
            and sum(ch.isdigit() for ch in cleaned) <= 2
        )
        if strong:
            strong_lines.append(cleaned)
        elif secondary:
            secondary_lines.append(cleaned)

    for line in strong_lines + secondary_lines:
        key = _dedupe_key(line)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(line)
        if len(candidates) >= 100:
            break

    return candidates
