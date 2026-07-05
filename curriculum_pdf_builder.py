from __future__ import annotations

import html
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from curriculum_models import LongPlan, MediumPlan

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:  # The requirements file installs these on Render.
    arabic_reshaper = None
    get_display = None


ROOT = Path(__file__).resolve().parent
EPS_LOGO = ROOT / "static" / "eps_logo.png"
SCHOOL_LOGO = ROOT / "static" / "school_logo.jpeg"

NAVY = colors.HexColor("#0A3568")
BLUE = colors.HexColor("#8DB5E3")
PALE_BLUE = colors.HexColor("#D9ECF7")
PALE_YELLOW = colors.HexColor("#FFF2C7")
LINE = colors.HexColor("#334155")
WHITE = colors.white
TEXT = colors.HexColor("#172033")

_FONT_REGULAR = "PlanSans"
_FONT_BOLD = "PlanSansBold"
_FONTS_READY = False


def _font_candidates() -> tuple[list[Path], list[Path]]:
    regular = [
        Path(os.getenv("PDF_FONT_REGULAR", "")),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    ]
    bold = [
        Path(os.getenv("PDF_FONT_BOLD", "")),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    ]
    return regular, bold


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if str(path) and path.is_file():
            return path
    return None


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular_candidates, bold_candidates = _font_candidates()
    regular = _first_existing(regular_candidates)
    bold = _first_existing(bold_candidates) or regular
    if regular is None:
        raise RuntimeError(
            "PDF export could not find an Arabic-capable system font. "
            "Set PDF_FONT_REGULAR and PDF_FONT_BOLD in Render Environment."
        )
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(regular)))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))
    _FONTS_READY = True


def _rtl_display(text: str) -> str:
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    output: list[str] = []
    for line in str(text).splitlines():
        if not line:
            output.append("")
            continue
        try:
            output.append(get_display(arabic_reshaper.reshape(line), base_dir="R"))
        except Exception:
            output.append(line)
    return "\n".join(output)


def _safe_text(text: str, rtl: bool = False) -> str:
    value = _rtl_display(str(text or "")) if rtl else str(text or "")
    return html.escape(value).replace("\n", "<br/>")


def _has_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(text or ""))


def _style(name: str, size: float = 7.0, leading: float | None = None, bold: bool = False,
           alignment: int = TA_LEFT, rtl: bool = False, color=TEXT) -> ParagraphStyle:
    return ParagraphStyle(
        name=name,
        fontName=_FONT_BOLD if bold else _FONT_REGULAR,
        fontSize=size,
        leading=leading or size * 1.3,
        textColor=color,
        alignment=alignment,
        wordWrap="RTL" if rtl else "LTR",
        spaceBefore=0,
        spaceAfter=0,
    )


def _p(text: str, size: float = 7.0, bold: bool = False, rtl: bool = False,
       align: int | None = None, color=TEXT, leading: float | None = None) -> Paragraph:
    if align is None:
        align = TA_RIGHT if rtl else TA_LEFT
    return Paragraph(
        _safe_text(text, rtl),
        _style(f"s-{size}-{bold}-{rtl}-{align}", size, leading, bold, align, rtl, color),
    )


def _header(title: str, rtl: bool) -> list:
    logo_path = EPS_LOGO if EPS_LOGO.exists() else SCHOOL_LOGO
    items: list = []
    if logo_path.exists():
        img = Image(str(logo_path))
        max_w, max_h = 105 * mm, 17 * mm
        scale = min(max_w / img.imageWidth, max_h / img.imageHeight)
        img.drawWidth = img.imageWidth * scale
        img.drawHeight = img.imageHeight * scale
        items.append(Table([[img]], colWidths=[landscape(A4)[0] - 24 * mm], style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])))
        items.append(Spacer(1, 2.5 * mm))
    items.append(_p(title, 14, True, rtl, TA_CENTER, NAVY, 17))
    items.append(Spacer(1, 3 * mm))
    return items


def _page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#B9C8D8"))
    canvas.setLineWidth(0.4)
    canvas.line(12 * mm, 8.5 * mm, landscape(A4)[0] - 12 * mm, 8.5 * mm)
    canvas.setFont(_FONT_REGULAR, 7)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(12 * mm, 5.4 * mm, "www.magdymath.com")
    canvas.drawRightString(landscape(A4)[0] - 12 * mm, 5.4 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _table(data, col_widths, header_rows: int = 0, font_size: float = 7.0,
           cell_padding: float = 3.2, extra_style: list | None = None) -> Table:
    table = Table(data, colWidths=col_widths, repeatRows=header_rows, hAlign="CENTER")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.55, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), cell_padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), cell_padding),
        ("TOPPADDING", (0, 0), (-1, -1), cell_padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), cell_padding),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
    ]
    if header_rows:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), BLUE),
            ("FONTNAME", (0, 0), (-1, header_rows - 1), _FONT_BOLD),
            ("ALIGN", (0, 0), (-1, header_rows - 1), "CENTER"),
            ("VALIGN", (0, 0), (-1, header_rows - 1), "MIDDLE"),
        ])
    if extra_style:
        commands.extend(extra_style)
    table.setStyle(TableStyle(commands))
    return table


def _metadata_medium(meta: dict, plan: MediumPlan, rtl: bool) -> Table:
    align = TA_RIGHT if rtl else TA_LEFT
    left = [
        _p(f"Year: {meta.get('academic_year', '')}", 7.5, True, False, align),
        _p(f"Teacher: {meta.get('teacher', '')}", 7.5, False, _has_arabic(meta.get('teacher', '')), align),
        _p("Term: 1", 7.5, True, False, align),
        _p("Grade:", 7.5, True, False, align),
        _p(meta.get('grade', ''), 7.5, False, rtl and _has_arabic(meta.get('grade', '')), align),
        _p("Title:", 7.5, True, False, align),
        _p(plan.title, 7.5, True, rtl and _has_arabic(plan.title), align),
        _p("Duration: 31 Aug - 11 Dec 2026 (14 weeks)", 7.5, True, False, align),
    ]
    right = [
        _p("Targets:", 8, True, False, align),
        _p(plan.targets, 7.4, False, rtl and _has_arabic(plan.targets), align, leading=9.5),
    ]
    return _table([[left, right]], [112 * mm, 161 * mm], extra_style=[
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


def _week_table(plan: MediumPlan, start: int, end: int, rtl: bool, include_break: bool = False) -> Table:
    headers = [
        _p("Week", 8, True, False, TA_CENTER),
        _p("Content", 8, True, False, TA_CENTER),
        _p("Learning Objectives", 8, True, False, TA_CENTER),
        _p("AI Literacy Objective / Integration", 7.4, True, False, TA_CENTER),
        _p("Resources & AI Tools", 8, True, False, TA_CENTER),
    ]
    dates = [
        "31 Aug - 4 Sep", "7 - 11 Sep", "14 - 18 Sep", "21 - 25 Sep", "28 Sep - 2 Oct", "5 - 9 Oct",
        "19 - 23 Oct", "26 - 30 Oct", "2 - 6 Nov", "9 - 13 Nov", "16 - 20 Nov", "23 - 27 Nov",
        "30 Nov - 4 Dec", "7 - 11 Dec",
    ]
    rows: list[list] = [headers]
    for idx in range(start, end):
        if include_break and idx == 6:
            rows.append([
                _p("MID-TERM BREAK\n12 - 18 Oct 2026", 7.1, True, False, TA_CENTER),
                "", "", "", "",
            ])
        week = plan.weeks[idx]
        rows.append([
            _p(f"W{idx + 1}\n{dates[idx]}", 7.4, True, False, TA_LEFT, leading=9.2),
            _p(week.content, 6.7, False, rtl, leading=8.3),
            _p(week.learning_objectives, 6.55, False, rtl, leading=8.2),
            _p(week.ai_literacy, 6.25, False, rtl, leading=7.9),
            _p(week.resources, 6.25, False, rtl, leading=7.9),
        ])
    extra = []
    if include_break:
        break_row = 1 + (6 - start)
        if 1 <= break_row < len(rows):
            extra.extend([
                ("BACKGROUND", (0, break_row), (-1, break_row), PALE_YELLOW),
                ("SPAN", (0, break_row), (0, break_row)),
            ])
    return _table(rows, [28 * mm, 48 * mm, 76 * mm, 57 * mm, 64 * mm], 1, 6.4, 2.6, extra)


def _label_value(label: str, value: str, rtl: bool, size: float = 7.0) -> list:
    align = TA_RIGHT if rtl else TA_LEFT
    return [
        _p(label, size, True, False, align),
        _p(value, size - 0.2, False, rtl and _has_arabic(value), align, leading=(size - 0.2) * 1.35),
    ]


def build_medium_pdf(meta: dict, plan: MediumPlan, output_path: Path) -> Path:
    _register_fonts()
    rtl = meta.get("language") == "Arabic"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=8 * mm, bottomMargin=12 * mm,
        title=plan.title, author=meta.get("teacher", ""),
    )
    story: list = []
    story.extend(_header("Medium Term Plan", False))
    story.append(_metadata_medium(meta, plan, rtl))
    story.append(Spacer(1, 4 * mm))
    story.append(_week_table(plan, 0, 7, rtl, include_break=True))

    story.append(PageBreak())
    story.extend(_header("Medium Term Plan - Weeks 8 to 14", False))
    story.append(_week_table(plan, 7, 14, rtl, include_break=False))
    story.append(Spacer(1, 3 * mm))
    summary = [[
        _label_value("Assessment Opportunities", plan.assessment_opportunities, rtl, 7.1),
        _label_value("21st Century Skills", plan.century_skills, rtl, 7.1),
        _label_value("Vocabulary / Key Words", plan.vocabulary, rtl, 7.1),
    ]]
    story.append(_table(summary, [91 * mm, 91 * mm, 91 * mm], font_size=6.8, cell_padding=4))
    story.append(Spacer(1, 2.5 * mm))
    details = [
        [
            _label_value("EPS Guiding Statement (Competences / HQL / Values)", plan.eps_guiding_statement, rtl, 7.0),
            _label_value("Global Citizenship", plan.global_citizenship, rtl, 7.0),
        ],
        [
            _label_value("Cross-curricular / Horizontal Articulation", plan.cross_curricular, rtl, 7.0),
            _label_value("National Identity Mark", plan.national_identity, rtl, 7.0),
        ],
    ]
    story.append(_table(details, [136.5 * mm, 136.5 * mm], font_size=6.7, cell_padding=4,
                        extra_style=[("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE)]))

    story.append(PageBreak())
    story.extend(_header("AI Integration, Safeguarding & Compliance", False))
    ai_rows = [
        [_label_value("1. AI Integration Approach", plan.ai_integration_approach, rtl, 8.0)],
        [_label_value("2. Guardrails & Prompt Controls", plan.guardrails_prompt_controls, rtl, 8.0)],
        [_label_value("3. Cognitive Integrity Strategy", plan.cognitive_integrity_strategy, rtl, 8.0)],
        [_label_value("4. AI Safeguarding & Responsible Use", plan.ai_safeguarding, rtl, 8.0)],
    ]
    story.append(_table(ai_rows, [273 * mm], font_size=7.5, cell_padding=5,
                        extra_style=[("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE)]))
    story.append(Spacer(1, 4 * mm))
    comp_header = [
        _p("Area", 7.5, True, False, TA_CENTER),
        _p("Milestone / Target", 7.5, True, False, TA_CENTER),
        _p("Responsible Person", 7.5, True, False, TA_CENTER),
        _p("Target Date", 7.5, True, False, TA_CENTER),
        _p("Status", 7.5, True, False, TA_CENTER),
    ]
    comp_rows = [comp_header]
    for item in plan.compliance[:4]:
        comp_rows.append([
            _p(item.area, 7.0, False, rtl), _p(item.milestone, 7.0, False, rtl),
            _p(item.responsible_person, 7.0, False, rtl), _p(item.target_date, 7.0, False, rtl),
            _p(item.status, 7.0, False, rtl),
        ])
    story.append(_table(comp_rows, [48 * mm, 87 * mm, 52 * mm, 43 * mm, 43 * mm], 1, 7.0, 4))

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output_path


def _metadata_long(meta: dict, rtl: bool) -> Table:
    return _table([[ 
        _label_value("Subject", meta.get("subject", ""), rtl, 8),
        _label_value("Teacher", meta.get("teacher", ""), rtl, 8),
        _label_value("Grade Group", meta.get("grade", ""), rtl, 8),
        _label_value("Academic Year", meta.get("academic_year", ""), rtl, 8),
    ]], [68.25 * mm] * 4, font_size=7.5, cell_padding=4,
        extra_style=[("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE)])


def build_long_pdf(meta: dict, plan: LongPlan, output_path: Path) -> Path:
    _register_fonts()
    rtl = meta.get("language") == "Arabic"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=8 * mm, bottomMargin=12 * mm,
        title="Long Term Plan", author=meta.get("teacher", ""),
    )
    story: list = []
    story.extend(_header("Long Term Plan", False))
    story.append(_metadata_long(meta, rtl))
    story.append(Spacer(1, 4 * mm))

    term_headers = [
        ("Term 1", "31 Aug 2026 - 11 Dec 2026"),
        ("Term 2", "4 Jan 2027 - 2 Apr 2027"),
        ("Term 3", "12 Apr 2027 - 2 Jul 2027"),
    ]
    term_row = []
    for title, dates in term_headers:
        term_row.append([_p(title, 9, True, False, TA_CENTER), _p(dates, 7, True, False, TA_CENTER)])
    story.append(_table([term_row], [91 * mm] * 3, font_size=7, cell_padding=4,
                        extra_style=[("BACKGROUND", (0, 0), (-1, -1), BLUE)]))
    story.append(Spacer(1, 2 * mm))

    half_titles = [
        "Autumn 1 (HT1)\n31 Aug - 9 Oct", "Autumn 2 (HT2)\n19 Oct - 11 Dec",
        "Spring 1 (HT3)\n4 Jan - 19 Feb", "Spring 2 (HT4)\n22 Feb - 2 Apr",
        "Summer 1 (HT5)\n12 Apr - 21 May", "Summer 2 (HT6)\n24 May - 2 Jul",
    ]
    headers = [_p(x, 7.1, True, False, TA_CENTER, leading=9.0) for x in half_titles]
    content = [_p(half.content, 6.35, False, rtl, leading=8.0) for half in plan.half_terms[:6]]
    assessment = [_p(half.summative_assessment, 6.25, False, rtl, leading=7.8) for half in plan.half_terms[:6]]
    curriculum = [headers, content, assessment]
    story.append(_table(curriculum, [45.5 * mm] * 6, 1, 6.4, 3.2,
                        extra_style=[
                            ("BACKGROUND", (0, 2), (-1, 2), PALE_YELLOW),
                        ]))
    story.append(Spacer(1, 4 * mm))
    story.append(_p("AI Implementation & Compliance Tracking (School Level)", 9.5, True, False, TA_CENTER, NAVY))
    story.append(Spacer(1, 2 * mm))
    comp_header = [
        _p("Area", 7.3, True, False, TA_CENTER), _p("Milestone / Target", 7.3, True, False, TA_CENTER),
        _p("Responsible Person", 7.3, True, False, TA_CENTER), _p("Target Date", 7.3, True, False, TA_CENTER),
        _p("Status", 7.3, True, False, TA_CENTER),
    ]
    comp_rows = [comp_header]
    for item in plan.compliance[:4]:
        comp_rows.append([
            _p(item.area, 6.8, False, rtl), _p(item.milestone, 6.8, False, rtl),
            _p(item.responsible_person, 6.8, False, rtl), _p(item.target_date, 6.8, False, rtl),
            _p(item.status, 6.8, False, rtl),
        ])
    story.append(_table(comp_rows, [48 * mm, 87 * mm, 52 * mm, 43 * mm, 43 * mm], 1, 6.8, 3.8))

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output_path
