from __future__ import annotations

import re

from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from math_format import build_equation

RLM = "\u200f"
EQ_RE = re.compile(r"\[\[EQ:(.+?)\]\]")
NUMBERED_RE = re.compile(r"^\s*[\u200e\u200f]*(\d+)[\.)-]?\s*(.*)$")
INLINE_NUMBER_RE = re.compile(r"([^\n])\s+((?:[\u200e\u200f])?\d{1,2}[\.)]\s+(?=[^\d]))")

HEADING_PREFIXES = (
    "تمهيد", "سؤال تشخيصي", "الاستجابة المتوقعة", "مثال محلول", "تدريب موجه",
    "تطبيق فردي", "نشاط تعاوني", "سؤال إثرائي", "سؤال تفكير عليا", "بطاقة خروج",
    "دور المعلم", "دور الطلاب", "دعم", "المستوى المتوقع", "متقدمون", "تكييفات",
    "خطأ متوقع", "معيار النجاح", "المنتج المتوقع", "المهمة", "التوجيه",
    "hook", "diagnostic question", "expected response", "worked example", "guided practice",
    "independent practice", "independent application", "collaborative task", "exit ticket",
    "teacher role", "student role", "support", "expected level", "advanced", "misconception",
    "success measure", "learning evidence", "hots",
)


def _normalise_lines(text, clean_text):
    value = clean_text(text)
    value = INLINE_NUMBER_RE.sub(r"\1\n\2", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return [line.strip() for line in value.split("\n") if line.strip()] or [""]


def _font_name(rtl: bool) -> str:
    return "Arial" if rtl else "Times New Roman"


def _add_text_run(paragraph, text, app_module, rtl, size, bold=False):
    if not text:
        return
    run = paragraph.add_run(text)
    app_module.set_run_font(run, _font_name(rtl), size, bold)


def _heading_split(line: str):
    if ":" not in line:
        return None
    possible, rest = line.split(":", 1)
    key = possible.strip().casefold()
    if len(possible.strip()) <= 46 and key in HEADING_PREFIXES:
        return possible.strip(), rest.lstrip()
    return None


def _append_content(paragraph, line, app_module, rtl, size):
    numbered = NUMBERED_RE.match(line)
    if numbered:
        prefix = f"{RLM}{numbered.group(1)}. {RLM}" if rtl else f"{numbered.group(1)}. "
        _add_text_run(paragraph, prefix, app_module, rtl, size, True)
        line = numbered.group(2)

    heading = _heading_split(line)
    if heading:
        _add_text_run(paragraph, heading[0] + ": ", app_module, rtl, size, True)
        line = heading[1]

    position = 0
    for equation in EQ_RE.finditer(line):
        _add_text_run(paragraph, line[position:equation.start()], app_module, rtl, size)
        paragraph._element.append(build_equation(equation.group(1).strip()))
        position = equation.end()
    _add_text_run(paragraph, line[position:], app_module, rtl, size)


def install_word_upgrade(app_module):
    """Fill the official template without changing its design or page geometry.

    This upgrade only supports Arabic direction, numbered content, bold inline
    headings, and native Word equations. It deliberately does not recolour cells,
    resize the logo, alter columns, change margins, remove rows, or rewrite labels.
    """

    def set_cell_text(cell, text, lang="en", size=8.0, bold=False):
        rtl = lang == "ar"
        cell.text = ""
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        lines = _normalise_lines(text, app_module.clean_text)

        for index, line in enumerate(lines):
            paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
            equation_match = EQ_RE.fullmatch(line)
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER
                if equation_match
                else (WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT)
            )
            app_module.set_paragraph_bidi(paragraph, rtl and not equation_match)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0

            if equation_match:
                paragraph._element.append(build_equation(equation_match.group(1).strip()))
            else:
                _append_content(paragraph, line, app_module, rtl, float(size))

    app_module.set_cell_text = set_cell_text
