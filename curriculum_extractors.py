from __future__ import annotations

import os
import re
import time
from pathlib import Path

TEXT_LIMIT = 24000
TOPIC_LIMIT = 100
NOISE = (
    "copyright", "all rights reserved", "publisher", "publishing", "isbn", "mcgraw",
    "pearson", "trademark", "www.", "http://", "https://", "©", "®", "™",
    "حقوق الطبع", "جميع الحقوق محفوظة", "الناشر", "الطبعة", "حقوق النشر",
    "المؤلف", "المراجع", "المصدر",
)
HEADS = (
    "unit", "chapter", "lesson", "section", "module", "topic", "strand", "domain",
    "الوحدة", "الفصل", "الدرس", "الموضوع", "المحور", "المجال", "الباب",
)
BODY = (
    "example", "exercise", "practice", "find the", "calculate", "suppose", "if the",
    "learning objective", "success criteria", "حل المثال", "أوجد", "احسب", "إذا كان",
    "مثال", "نشاط", "ناقش", "فسر", "علل", "اختر الإجابة",
)
GENERIC = {
    "contents", "table of contents", "index", "glossary", "references", "introduction",
    "answers", "answer key", "review", "assessment", "guided practice", "homework",
    "objectives", "resources", "الفهرس", "المحتويات", "المقدمة", "المراجع",
    "الإجابات", "مراجعة", "تقويم", "أهداف التعلم", "المصادر", "الواجب",
}


def _normal(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[\t\u00a0]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:TEXT_LIMIT]


def _clean(line: str) -> str:
    line = re.sub(r"^\[HEADING\]\s*", "", str(line or ""), flags=re.I)
    line = re.sub(r"\.{2,}\s*\d+\s*$", "", line)
    line = re.sub(r"^\s*(?:page|صفحة)\s*\d+\s*$", "", line, flags=re.I)
    return re.sub(r"\s+", " ", line).strip(" -–—|:;,.\t")


def _bad(line: str) -> bool:
    line = _clean(line)
    low = line.casefold()
    words = line.split()
    if not line or low in GENERIC or any(x in low for x in NOISE + BODY):
        return True
    if len(line) > 120 or len(words) > 17:
        return True
    if re.search(r"\.(?:com|org|net|edu|ae)\b", low) or "@" in line:
        return True
    if re.fullmatch(r"[\d\W_]+", line):
        return True
    if sum(c.isdigit() for c in line) >= 6:
        return True
    return False


def _strong(raw: str, line: str) -> bool:
    low = line.casefold()
    return (
        str(raw).lstrip().lower().startswith("[heading]")
        or any(re.match(rf"^{re.escape(w)}\b", low) for w in HEADS)
        or bool(re.match(r"^\d+(?:\.\d+){1,3}\s+\S", line))
    )


def _short(line: str) -> bool:
    return 1 <= len(line.split()) <= 11 and len(line) <= 100 and not re.search(r"[.!?؟؛]$", line)


def _key(line: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", "", line.casefold())


def extract_pdf(path: Path) -> str:
    import fitz

    max_pages = max(8, min(48, int(os.getenv("CURRICULUM_PDF_MAX_PAGES", "32"))))
    seconds = max(4.0, min(15.0, float(os.getenv("CURRICULUM_EXTRACT_SECONDS", "10"))))
    deadline = time.monotonic() + seconds
    out: list[str] = []

    with fitz.open(path) as pdf:
        if getattr(pdf, "needs_pass", False):
            raise ValueError("The PDF is password protected.")

        try:
            toc = pdf.get_toc(simple=True) or []
        except Exception:
            toc = []
        for item in toc[:200]:
            if len(item) >= 2:
                title = _clean(str(item[1]))
                if not _bad(title):
                    out.append("[HEADING] " + title)
        if len(out) >= 4:
            return _normal("\n".join(out))

        for page_no in range(min(len(pdf), max_pages)):
            if time.monotonic() >= deadline or len("\n".join(out)) >= TEXT_LIMIT:
                break
            try:
                text = pdf[page_no].get_text("text", sort=True) or ""
            except Exception:
                continue
            kept = 0
            for raw in text.splitlines():
                line = _clean(raw)
                if _bad(line) or not (_strong(raw, line) or _short(line)):
                    continue
                out.append(("[HEADING] " if _strong(raw, line) else "") + line)
                kept += 1
                if kept >= 14:
                    break
    return _normal("\n".join(out))


def extract_docx(path: Path) -> str:
    from docx import Document

    deadline = time.monotonic() + 10
    doc = Document(path)
    out: list[str] = []
    total = 0
    for p in doc.paragraphs:
        if time.monotonic() >= deadline or total >= TEXT_LIMIT:
            break
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style else ""
        value = ("[HEADING] " if "heading" in style or "title" in style else "") + text
        out.append(value)
        total += len(value)
    for table in doc.tables[:12]:
        if time.monotonic() >= deadline or total >= TEXT_LIMIT:
            break
        for row in table.rows[:60]:
            value = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
            if value:
                out.append(value)
                total += len(value)
    return _normal("\n".join(out))


def extract_pptx(path: Path) -> str:
    from pptx import Presentation

    out: list[str] = []
    for slide in Presentation(path).slides[:100]:
        for shape in slide.shapes:
            text = getattr(shape, "text", "")
            if not isinstance(text, str):
                continue
            for raw in text.splitlines():
                line = _clean(raw)
                if not _bad(line) and (_strong(raw, line) or _short(line)):
                    out.append(("[HEADING] " if _strong(raw, line) else "") + line)
        if len("\n".join(out)) >= TEXT_LIMIT:
            break
    return _normal("\n".join(out))


def extract_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    out: list[str] = []
    try:
        for ws in wb.worksheets[:10]:
            for index, row in enumerate(ws.iter_rows(values_only=True), 1):
                if index > 250:
                    break
                values = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if values:
                    out.append(" | ".join(values))
                if len("\n".join(out)) >= TEXT_LIMIT:
                    return _normal("\n".join(out))
    finally:
        wb.close()
    return _normal("\n".join(out))


def extract_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        with Image.open(path) as image:
            image.thumbnail((2000, 2000))
            return _normal(pytesseract.image_to_string(
                image, lang=os.getenv("TESSERACT_LANG", "eng+ara"), timeout=7
            ))
    except Exception:
        return ""


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pptx":
        return extract_pptx(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return extract_image(path)
    if suffix in {".txt", ".md", ".csv"}:
        return _normal(path.read_text(encoding="utf-8", errors="ignore"))
    raise ValueError("Unsupported file type")


def candidate_topics(source_text: str, manual_topics: str = "") -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        line = _clean(raw)
        key = _key(line)
        if not key or key in seen or _bad(line):
            return
        seen.add(key)
        out.append(line)

    for raw in re.split(r"[\n;•]+", manual_topics or ""):
        add(raw)

    strong: list[str] = []
    weak: list[str] = []
    for raw_line in (source_text or "").splitlines():
        parts = raw_line.split("|") if "|" in raw_line else [raw_line]
        for raw in parts:
            line = _clean(raw)
            if _bad(line):
                continue
            if _strong(raw, line):
                strong.append(line)
            elif _short(line):
                weak.append(line)

    for item in strong:
        add(item)
        if len(out) >= TOPIC_LIMIT:
            return out
    for item in weak[:40 if len(out) < 8 else 18]:
        add(item)
        if len(out) >= TOPIC_LIMIT:
            break
    return out
