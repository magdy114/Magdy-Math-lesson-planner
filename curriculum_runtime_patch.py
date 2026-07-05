from __future__ import annotations

import os
import re
import time
from pathlib import Path


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


def install(core) -> None:
    original_extract = core.extract_curriculum_text

    def fast_extract(path: Path) -> str:
        if Path(path).suffix.lower() == ".pdf":
            return _fast_pdf(Path(path))
        return original_extract(path)

    def local_refine(meta, source_text, candidates, language):
        from curriculum_ai import clean_topics
        return clean_topics(candidates)

    core.extract_curriculum_text = fast_extract
    core.refine_topics = local_refine
