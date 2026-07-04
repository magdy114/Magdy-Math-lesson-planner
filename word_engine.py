import io
import re
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from math_format import build_equation

RLM = "\u200f"
EQ_RE = re.compile(r"\[\[EQ:(.+?)\]\]")
NUMBERED_RE = re.compile(r"^\s*[\u200e\u200f]*(\d+)[\.)]\s*(.*)$")
INLINE_NUMBER_RE = re.compile(r"([^\n])\s+((?:[\u200e\u200f])?\d{1,2}[\.)]\s+(?=[^\d]))")
BRAND_MARKERS = ("www.magdymath.com", "prepared by mr. magdy elsayed")

HEADING_PREFIXES = (
    "تمهيد", "سؤال تشخيصي", "مثال محلول", "تدريب موجه", "تطبيق فردي",
    "نشاط تعاوني", "سؤال إثرائي", "hots", "بطاقة خروج", "دور المعلم",
    "دور الطلاب", "دعم", "المستوى المتوقع", "متقدمون", "iep/apl",
    "hook", "diagnostic question", "worked example", "guided practice",
    "independent practice", "collaborative task", "exit ticket",
    "teacher role", "student role", "support", "expected level", "advanced"
)

TABLE_LABELS = (
    "lesson plan", "teacher:", "subject:", "date:", "class:", "topic:", "periods:",
    "key words", "keywords", "primary sdg", "strategies", "learning outcomes",
    "success criteria", "lesson structure", "starter", "main activities",
    "teacher-led", "student-led", "plenary", "kpi afl", "21 century",
    "resources", "curriculum", "reflection"
)


def _normalize_lines(text, clean_text):
    value = clean_text(text)
    value = INLINE_NUMBER_RE.sub(r"\1\n\2", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return [line.strip() for line in value.split("\n") if line.strip()] or [""]


def _font_name(rtl):
    return "Arial" if rtl else "Aptos"


def _add_text_run(paragraph, text, app_module, rtl, size, bold=False, color=None):
    if not text:
        return
    run = paragraph.add_run(text)
    app_module.set_run_font(run, _font_name(rtl), size, bold)
    if color is not None:
        run.font.color.rgb = color


def _append_mixed_content(paragraph, line, app_module, rtl, size):
    numbered = NUMBERED_RE.match(line)
    if numbered:
        number_text = numbered.group(1)
        body = numbered.group(2)
        prefix = f"{RLM}{number_text}. {RLM}" if rtl else f"{number_text}. "
        _add_text_run(paragraph, prefix, app_module, rtl, size, True, RGBColor(31, 78, 121))
        line = body

    heading_match = None
    if ":" in line:
        possible, rest = line.split(":", 1)
        if len(possible.strip()) <= 34 and possible.strip().lower() in HEADING_PREFIXES:
            heading_match = (possible.strip(), rest.lstrip())

    if heading_match:
        _add_text_run(
            paragraph,
            heading_match[0] + ": ",
            app_module,
            rtl,
            size,
            True,
            RGBColor(31, 78, 121),
        )
        line = heading_match[1]

    pos = 0
    for equation in EQ_RE.finditer(line):
        before = line[pos:equation.start()]
        _add_text_run(paragraph, before, app_module, rtl, size, False)
        paragraph._element.append(build_equation(equation.group(1).strip()))
        pos = equation.end()
    _add_text_run(paragraph, line[pos:], app_module, rtl, size, False)


def install_word_upgrade(app_module):
    def set_cell_text(cell, text, lang="en", size=8.0, bold=False):
        rtl = lang == "ar"
        body_size = max(float(size) + 0.65, 8.0)
        cell.text = ""
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        lines = _normalize_lines(text, app_module.clean_text)

        for index, line in enumerate(lines):
            paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
            equation_only = bool(EQ_RE.fullmatch(line))
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER
                if equation_only
                else (WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT)
            )
            app_module.set_paragraph_bidi(paragraph, rtl and not equation_only)
            paragraph.paragraph_format.space_before = Pt(1 if equation_only else 0)
            paragraph.paragraph_format.space_after = Pt(2 if equation_only else 1.5)
            paragraph.paragraph_format.line_spacing = 1.08
            paragraph.paragraph_format.keep_together = True

            if equation_only:
                paragraph._element.append(build_equation(EQ_RE.fullmatch(line).group(1).strip()))
            else:
                _append_mixed_content(paragraph, line, app_module, rtl, body_size)

    app_module.set_cell_text = set_cell_text
    original = app_module.generate_docx

    def generate_docx(lesson):
        return enhance_docx(original(lesson), app_module.logger)

    app_module.generate_docx = generate_docx


def remove_fixed_height(row):
    props = row._tr.get_or_add_trPr()
    for node in list(props.findall(qn("w:trHeight"))):
        props.remove(node)


def clear_repeat_header(row):
    props = row._tr.get_or_add_trPr()
    for node in list(props.findall(qn("w:tblHeader"))):
        props.remove(node)


def set_cell_margins(cell):
    props = cell._tc.get_or_add_tcPr()
    margins = props.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        props.append(margins)
    for name, value in (("top", 55), ("start", 75), ("bottom", 55), ("end", 75)):
        node = margins.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _remove_paragraph(paragraph):
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def remove_branding_line(doc):
    for section in doc.sections:
        for paragraph in list(section.header.paragraphs):
            text = paragraph.text.strip().lower()
            if any(marker in text for marker in BRAND_MARKERS):
                _remove_paragraph(paragraph)
    for paragraph in list(doc.paragraphs):
        text = paragraph.text.strip().lower()
        if any(marker in text for marker in BRAND_MARKERS):
            _remove_paragraph(paragraph)


def _table_signature(table):
    labels = []
    seen_cells = set()
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen_cells:
                continue
            seen_cells.add(key)
            text = re.sub(r"\s+", " ", cell.text.strip().lower())
            for label in TABLE_LABELS:
                if label in text:
                    labels.append(label)
    return (len(table.rows), len(table.columns), tuple(sorted(set(labels))))


def remove_duplicate_tables(doc):
    seen = set()
    for table in list(doc.tables):
        signature = _table_signature(table)
        if len(signature[2]) < 5:
            continue
        if signature in seen:
            parent = table._element.getparent()
            if parent is not None:
                parent.remove(table._element)
        else:
            seen.add(signature)


def style_document_tables(doc):
    for table in doc.tables:
        table.autofit = True
        for row in table.rows:
            clear_repeat_header(row)
            remove_fixed_height(row)
            for cell in row.cells:
                set_cell_margins(cell)
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_before = Pt(0)
                    paragraph.paragraph_format.space_after = Pt(1.5)
                    paragraph.paragraph_format.line_spacing = 1.08
                    label = paragraph.text.strip().lower()
                    if label in ("lesson structure", "lesson plan"):
                        paragraph.paragraph_format.keep_with_next = True
                        for run in paragraph.runs:
                            run.font.bold = True
                            run.font.size = Pt(10.5)


def enhance_docx(data, logger):
    doc = Document(io.BytesIO(data))
    remove_branding_line(doc)
    remove_duplicate_tables(doc)
    style_document_tables(doc)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()
