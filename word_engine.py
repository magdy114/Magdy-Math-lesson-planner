import io
import re
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from math_format import build_equation

RLM='\u200f'
EQ_RE=re.compile(r'\[\[EQ:(.+?)\]\]')

def install_word_upgrade(app_module):
    def set_cell_text(cell,text,lang='en',size=8.0,bold=False):
        rtl=lang=='ar'
        cell.text=''
        cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
        for index,line in enumerate(app_module.clean_text(text).split('\n') if text else ['']):
            line=line.strip()
            paragraph=cell.paragraphs[0] if index==0 else cell.add_paragraph()
            equation_only=bool(EQ_RE.fullmatch(line))
            paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER if equation_only else (WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT)
            app_module.set_paragraph_bidi(paragraph,rtl and not equation_only)
            paragraph.paragraph_format.space_before=Pt(0)
            paragraph.paragraph_format.space_after=Pt(1)
            paragraph.paragraph_format.line_spacing=1.06
            match=re.match(r'^\s*[\u200e\u200f]*(\d+)[\.)]\s*(.*)$',line)
            if match and rtl: line=f'{RLM}{match.group(1)}. {RLM}{match.group(2)}'
            pos=0
            for equation in EQ_RE.finditer(line):
                before=line[pos:equation.start()]
                if before:
                    run=paragraph.add_run(before)
                    app_module.set_run_font(run,'Arial' if rtl else 'Aptos',max(size+.5,7.4),True)
                paragraph._element.append(build_equation(equation.group(1).strip()))
                pos=equation.end()
            after=line[pos:]
            if after:
                run=paragraph.add_run(after)
                app_module.set_run_font(run,'Arial' if rtl else 'Aptos',max(size+.5,7.4),True)
    app_module.set_cell_text=set_cell_text
    original=app_module.generate_docx
    def generate_docx(lesson):
        return enhance_docx(original(lesson),app_module.logger)
    app_module.generate_docx=generate_docx

def remove_fixed_height(row):
    props=row._tr.get_or_add_trPr()
    for node in list(props.findall(qn('w:trHeight'))): props.remove(node)
    if props.find(qn('w:cantSplit')) is None: props.append(OxmlElement('w:cantSplit'))

def set_cell_margins(cell):
    props=cell._tc.get_or_add_tcPr()
    margins=props.first_child_found_in('w:tcMar')
    if margins is None:
        margins=OxmlElement('w:tcMar'); props.append(margins)
    for name,value in (('top',40),('start',65),('bottom',40),('end',65)):
        node=margins.find(qn(f'w:{name}'))
        if node is None:
            node=OxmlElement(f'w:{name}'); margins.append(node)
        node.set(qn('w:w'),str(value)); node.set(qn('w:type'),'dxa')

def add_page_break_before(paragraph):
    props=paragraph._p.get_or_add_pPr()
    node=props.find(qn('w:pageBreakBefore'))
    if node is None:
        node=OxmlElement('w:pageBreakBefore'); props.append(node)
    node.set(qn('w:val'),'1')

def add_branding(doc,logger):
    brand='www.magdymath.com   |   Prepared by Mr. Magdy ElSayed'
    for section in doc.sections:
        header=section.header
        try:
            for extent in header._element.xpath('.//wp:extent'):
                extent.set('cx',str(int(3.65*914400)))
                extent.set('cy',str(int(.92*914400)))
        except Exception:
            logger.exception('Header logo resize failed')
        if brand not in '\n'.join(p.text for p in header.paragraphs):
            p=header.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(2)
            run=p.add_run(brand); run.font.name='Aptos'; run.font.size=Pt(8.5); run.font.bold=True
            run.font.color.rgb=RGBColor(37,76,122)

def enhance_docx(data,logger):
    doc=Document(io.BytesIO(data)); add_branding(doc,logger)
    for table in doc.tables:
        for row in table.rows:
            remove_fixed_height(row)
            for cell in row.cells:
                set_cell_margins(cell)
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_before=Pt(0)
                    paragraph.paragraph_format.space_after=Pt(1)
                    paragraph.paragraph_format.line_spacing=1.05
                    label=paragraph.text.strip().lower()
                    if label in ('lesson structure','lesson plan'):
                        paragraph.paragraph_format.keep_with_next=True
                        if label=='lesson structure': add_page_break_before(paragraph)
    output=io.BytesIO(); doc.save(output); return output.getvalue()
