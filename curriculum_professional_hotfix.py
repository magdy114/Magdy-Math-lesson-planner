from __future__ import annotations

import re
from pathlib import Path

from docx.oxml.ns import qn

IMAGE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".jfif", ".bmp", ".gif",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}


def install(core) -> None:
    import curriculum_document_builder as builder
    import curriculum_professional_patch as professional
    import curriculum_runtime_patch as runtime

    original_generate = core.generate_medium
    original_set_cell_text = builder._set_cell_text

    def extract(path: Path) -> str:
        file_path = Path(path)
        if file_path.suffix.lower() in IMAGE_SUFFIXES:
            text = runtime._fast_image(file_path)
            if text:
                return professional._normalise(text)
        return professional.robust_extract(file_path)

    def clean_text(value: str) -> str:
        text = professional._normalise(value)
        text = re.sub(r"[�□■▢▣▤▥▦▧▨▩]+", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def set_cell_text(cell, text: str, size: float = 8, bold_first: bool = False, rtl: bool = False, center: bool = False):
        original_set_cell_text(cell, clean_text(text), size, bold_first, rtl, center)
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.name = "Arial"
                properties = run._element.get_or_add_rPr()
                fonts = properties.rFonts
                if fonts is None:
                    from docx.oxml import OxmlElement
                    fonts = OxmlElement("w:rFonts")
                    properties.append(fonts)
                for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    fonts.set(qn(key), "Arial")

    def generate(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = ""):
        plan = original_generate(meta, source_text, topics, language, instructions)
        lang = professional._language(language)
        subject = professional._subject(meta.get("subject", ""), lang)
        grade = professional._grade(meta.get("grade", ""), lang)
        meta["subject"] = subject
        meta["grade"] = grade
        plan.title = (
            f"الخطة متوسطة المدى - {subject} - {grade}"
            if lang == "Arabic"
            else f"Medium Term Plan - {subject} - {grade}"
        )
        return professional._clean_plan(plan, lang)

    core.extract_curriculum_text = extract
    core.generate_medium = generate
    builder._set_cell_text = set_cell_text
