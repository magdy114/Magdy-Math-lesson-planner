from __future__ import annotations

import os
import re
import uuid
from html import unescape
from pathlib import Path

from werkzeug.utils import secure_filename

import lesson_source_grounding_patch as source_grounding
import lesson_math_family_hotfix
import lesson_scanned_pdf_vision


def _topic_hint(prefix: str) -> str:
    try:
        from flask import request

        match = re.search(r"(\d+)$", str(prefix or ""))
        index = max(0, int(match.group(1)) - 1) if match else 0
        topics = request.form.getlist("topic[]") or [request.form.get("topic", "")]
        return topics[index].strip() if index < len(topics) else ""
    except Exception:
        return ""


def _extract_pdf_for_topic(path: Path, topic: str) -> str:
    """Search the whole PDF for the lesson title, then retain relevant neighboring pages."""
    try:
        import fitz

        max_pages = max(12, min(140, int(os.getenv("LESSON_PDF_SEARCH_PAGES", "100"))))
        pages: list[tuple[int, str]] = []
        with fitz.open(path) as pdf:
            for page_index in range(min(len(pdf), max_pages)):
                text = (pdf[page_index].get_text("text", sort=True) or "").strip()
                if text:
                    pages.append((page_index, text))

        if not pages:
            return source_grounding._extract_pdf(path)

        query_tokens = set(source_grounding._tokens(topic))
        topic_phrase = source_grounding._clean(topic).casefold()
        ranked: list[tuple[float, int]] = []
        page_map = {page_index: text for page_index, text in pages}
        for page_index, text in pages:
            page_tokens = source_grounding.Counter(source_grounding._tokens(text))
            overlap = sum(min(page_tokens[token], 6) for token in query_tokens)
            phrase_bonus = 25 if topic_phrase and len(topic_phrase) >= 4 and topic_phrase in text.casefold() else 0
            heading_bonus = 4 if re.search(r"(?:lesson|unit|chapter|section|الدرس|الوحدة|الفصل|الموضوع)", text[:500], re.I) else 0
            ranked.append((overlap * 4 + phrase_bonus + heading_bonus, page_index))

        selected = {pages[0][0]}
        for score, page_index in sorted(ranked, reverse=True)[:8]:
            if score <= 0 and len(selected) >= 3:
                continue
            selected.add(page_index)
            if page_index - 1 in page_map:
                selected.add(page_index - 1)
            if page_index + 1 in page_map:
                selected.add(page_index + 1)

        combined = "\n\n".join(
            f"[Page {page_index + 1}]\n{page_map[page_index]}"
            for page_index in sorted(selected)
            if page_index in page_map
        )
        return source_grounding.select_relevant_source(
            combined,
            topic,
            max_chars=source_grounding.EXTRACT_MAX_CHARS,
        )
    except Exception:
        return source_grounding._extract_pdf(path)


def _install_clean_generate_error(core) -> None:
    app = core.app
    if getattr(app, "_clean_lesson_generate_errors_installed", False):
        return

    original_generate = app.view_functions.get("generate")
    if original_generate is None:
        return

    def generate_with_clean_errors(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        response = app.make_response(result)
        content_type = response.headers.get("Content-Type", "")
        if response.status_code >= 400 and "text/html" in content_type:
            page = response.get_data(as_text=True)
            match = re.search(r'<div class="alert error">(.*?)</div>', page, re.I | re.S)
            detail = match.group(1) if match else "تعذر إنشاء ملف Word بسبب خطأ داخلي مؤقت."
            detail = re.sub(r"<[^>]+>", " ", detail)
            detail = re.sub(r"\s+", " ", unescape(detail)).strip()
            if len(detail) > 520:
                detail = detail[:517].rstrip() + "..."
            return app.response_class(detail, status=response.status_code, mimetype="text/plain")
        return result

    app.view_functions["generate"] = generate_with_clean_errors
    app._clean_lesson_generate_errors_installed = True


def _configure_upload_limit(core) -> None:
    try:
        configured = int(os.getenv("MAX_UPLOAD_MB", "128"))
    except Exception:
        configured = 128
    upload_mb = max(128, min(160, configured))
    core.app.config["MAX_CONTENT_LENGTH"] = upload_mb * 1024 * 1024
    core.app.config["MAX_UPLOAD_MB"] = upload_mb


def install(core) -> None:
    lesson_math_family_hotfix.install(core)
    _configure_upload_limit(core)
    _install_clean_generate_error(core)
    if getattr(core, "_lesson_upload_relevance_installed", False):
        return

    core.ALLOWED_EXTENSIONS.update({"xlsx", "md", "csv"})

    def save_uploaded_file(storage, prefix: str):
        if not storage or not storage.filename:
            return "", ""
        ext = core.file_ext(storage.filename)
        if ext not in core.ALLOWED_EXTENSIONS:
            return storage.filename, f"[Unsupported file type: {ext}]"

        safe_original = secure_filename(storage.filename) or f"source.{ext or 'txt'}"
        saved = Path(core.UPLOAD_DIR) / f"{prefix}_{uuid.uuid4().hex}_{safe_original}"
        storage.save(str(saved))
        topic = _topic_hint(prefix)
        extracted = (
            _extract_pdf_for_topic(saved, topic)
            if ext == "pdf"
            else source_grounding._extract_file(saved)
        )
        if ext == "pdf" and not extracted.strip():
            extracted = lesson_scanned_pdf_vision.extract_scanned_pdf(saved, topic)
        if not extracted.strip():
            return storage.filename, (
                "[The uploaded file is image-only and no lesson text could be read. "
                "Check that OPENAI_API_KEY is available, or upload only the relevant lesson pages as a smaller PDF/image.]"
            )
        return storage.filename, extracted

    core.save_uploaded_file = save_uploaded_file
    core._lesson_upload_relevance_installed = True
