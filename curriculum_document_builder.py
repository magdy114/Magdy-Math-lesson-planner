from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from curriculum_models import LongPlan, MediumPlan


ROOT = Path(__file__).resolve().parent
MEDIUM_TEMPLATE = ROOT / "word_templates" / "medium_term_template.docx"
LONG_TEMPLATE = ROOT / "word_templates" / "long_term_template.docx"


def _remove_content_keep_tables(cell) -> None:
    tc = cell._tc
    for child in list(tc):
        if child.tag in {qn("w:tcPr"), qn("w:tbl")}:
            continue
        tc.remove(child)


def _set_bidi(paragraph, enabled: bool) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    bidi = ppr.find(qn("w:bidi"))
    if enabled and bidi is None:
        bidi = OxmlElement("w:bidi")
        ppr.append(bidi)
    elif not enabled and bidi is not None:
        ppr.remove(bidi)


def _set_cell_text(cell, text: str, font_size: float = 8.0, bold_first: bool = False, rtl: bool = False, preserve_nested_tables: bool = False) -> None:
    nested = list(cell.tables) if preserve_nested_tables else []
    _remove_content_keep_tables(cell) if preserve_nested_tables else _clear_cell(cell)
    lines = (text or "").splitlines() or [""]
    new_paragraphs = []
    for idx, line in enumerate(lines):
        p = cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        _set_bidi(p, rtl)
        run = p.add_run(line)
        run.bold = bold_first and idx == 0
        run.font.size = Pt(font_size)
        run.font.name = "Arial"
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Arial")
        new_paragraphs.append(p)
    if preserve_nested_tables and nested:
        tbl_el = nested[0]._tbl
        for p in new_paragraphs:
            tbl_el.addprevious(p._p)
        closing = cell.add_paragraph()
        closing.paragraph_format.space_before = Pt(0)
        closing.paragraph_format.space_after = Pt(0)
        closing.paragraph_format.line_spacing = 1.0
        closing.add_run("").font.size = Pt(1)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP if preserve_nested_tables else WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _clear_cell(cell) -> None:
    tc = cell._tc
    for child in list(tc):
        if child.tag == qn("w:tcPr"):
            continue
        tc.remove(child)


def _cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _set_row_min_height(row, twips: int) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    for old in list(tr_pr.findall(qn("w:trHeight"))):
        tr_pr.remove(old)
    height = OxmlElement("w:trHeight")
    height.set(qn("w:val"), str(twips))
    height.set(qn("w:hRule"), "atLeast")
    tr_pr.append(height)


def _style_all_runs(cell, font_size: float, rtl: bool = False) -> None:
    for p in cell.paragraphs:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        _set_bidi(p, rtl)
        for r in p.runs:
            r.font.size = Pt(font_size)
            r.font.name = "Arial"
            r._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Arial")


def _compliance_line(item) -> list[str]:
    return [item.area, item.milestone, item.responsible_person, item.target_date, item.status]


def build_medium(meta: dict, plan: MediumPlan, output_path: Path) -> Path:
    doc = Document(MEDIUM_TEMPLATE)
    rtl = meta.get("language") == "Arabic"

    if doc.paragraphs:
        p = doc.paragraphs[0]
        p.text = plan.title
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.bold = True
            run.font.size = Pt(15)

    top = doc.tables[0]
    _set_cell_text(top.cell(0, 0), f"Year: {meta['academic_year']}\nTeacher: {meta['teacher']}", 9, True, rtl)
    _set_cell_text(top.cell(0, 1), f"Term: 1\nGrade: {meta['grade']}", 9, True, rtl)
    _set_cell_text(top.cell(0, 2), f"Targets:\n{plan.targets}", 8, True, rtl)
    _set_cell_text(top.cell(1, 0), f"Title: {plan.title}", 9, True, rtl)
    _set_cell_text(top.cell(2, 0), "Duration: 31 Aug - 11 Dec 2026 (14 weeks)", 9, True, rtl)

    weekly = doc.tables[1]
    week_rows = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15]
    for item, row_idx in zip(plan.weeks[:14], week_rows):
        row = weekly.rows[row_idx]
        _cant_split(row)
        _set_cell_text(row.cells[1], item.content, 6.7, False, rtl)
        _set_cell_text(row.cells[2], item.learning_objectives, 6.4, False, rtl)
        _set_cell_text(row.cells[3], item.ai_literacy, 6.2, False, rtl)
        _set_cell_text(row.cells[4], item.resources, 6.2, False, rtl)
    for c in range(1, 5):
        _set_cell_text(weekly.rows[7].cells[c], "", 7, False, rtl)

    summary = doc.tables[2]
    _cant_split(summary.rows[0])
    _set_cell_text(summary.cell(0, 0), f"Assessment Opportunities:\n{plan.assessment_opportunities}", 6.8, True, rtl)
    _set_cell_text(summary.cell(0, 1), f"21st Century Skills:\n{plan.century_skills}", 6.8, True, rtl)
    _set_cell_text(summary.cell(0, 2), f"Vocabulary/Key Words:\n{plan.vocabulary}", 6.8, True, rtl)

    footer = doc.tables[3]
    for footer_row in footer.rows[:4]:
        _cant_split(footer_row)
    _set_cell_text(footer.cell(0, 0), f"Link to EPS Guiding Statement (Competences/HQL/Values):\n{plan.eps_guiding_statement}", 7.0, True, rtl)
    _set_cell_text(footer.cell(1, 0), f"Global Citizenship:\n{plan.global_citizenship}", 7.0, True, rtl)
    _set_cell_text(footer.cell(2, 0), f"Cross-curricular / horizontal articulation:\n{plan.cross_curricular}", 7.0, True, rtl)

    # Preserve the official National Identity checkbox controls in this row.
    _cant_split(footer.rows[3])

    # Preserve all official AI/compliance dropdowns and the date field exactly as supplied.
    # Teachers can make their own selections in Microsoft Word.
    _cant_split(footer.rows[4])
    _set_row_min_height(footer.rows[4], 5600)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path


def _remove_trailing_empty_paragraphs(doc) -> None:
    body = doc._element.body
    children = list(body)
    last_tbl_index = max((i for i, el in enumerate(children) if el.tag == qn("w:tbl")), default=-1)
    for i, el in enumerate(list(body)):
        if i > last_tbl_index and el.tag == qn("w:p"):
            text = "".join(el.itertext()).strip()
            if not text:
                body.remove(el)


def build_long(meta: dict, plan: LongPlan, output_path: Path) -> Path:
    doc = Document(LONG_TEMPLATE)
    rtl = meta.get("language") == "Arabic"

    metadata = doc.tables[0]
    _set_cell_text(metadata.cell(0, 0), f"Subject: {meta['subject']}\nTeacher: {meta['teacher']}", 9, True, rtl)
    _set_cell_text(metadata.cell(0, 1), f"Grade Group: {meta['grade']}", 9, True, rtl)
    _set_cell_text(metadata.cell(0, 2), f"Academic Year: {meta['academic_year']}", 9, True, rtl)

    curriculum = doc.tables[1]
    for idx, half in enumerate(plan.half_terms[:6], start=1):
        _set_cell_text(curriculum.cell(2, idx), half.content, 7.6, False, rtl)
        _set_cell_text(curriculum.cell(3, idx), half.summative_assessment, 7.4, False, rtl)
    _cant_split(curriculum.rows[2])
    _cant_split(curriculum.rows[3])

    compliance = doc.tables[2]
    # Preserve the four official rows and all 20 dropdown controls. The school-level
    # compliance section stays as “Select…” for the user to complete in Microsoft Word.
    for row in compliance.rows[1:5]:
        _cant_split(row)

    _remove_trailing_empty_paragraphs(doc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path
