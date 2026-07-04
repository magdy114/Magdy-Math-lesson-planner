import io
import re
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from math_format import build_equation

RLM='\u200f'
EQ_RE=re.compile(r'\[\[EQ:(.+?)\]\]')

def install_word_upgrade(app_module):
    def set_cell_text(cell,text,lang='en',size=8.0,bold=False):
        rtl=lang=='ar'
        cell.text=''
        cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
        for index,line in enumerate(app_module.clean_text(text).split('\n') if text else ['']):
            paragraph=cell.paragraphs[0] if index==0 else cell.add_paragraph()
            paragraph.alignment=WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
            app_module.set_paragraph_bidi(paragraph,rtl)
            paragraph.paragraph_format.space_before=Pt(0)
            paragraph.paragraph_format.space_after=Pt(1)
            paragraph.paragraph_format.line_spacing=1.05
            match=re.match(r'^\s*(\d+)[\.)]\s*(.*)$',line)
            if match and rtl: line=f'{RLM}{match.group(1)}. {RLM}{match.group(2)}'
            pos=0
            for equation in EQ_RE.finditer(line):
                before=line[pos:equation.start()]
                if before:
                    run=paragraph.add_run(before)
                    app_module.set_run_font(run,'Arial' if rtl else 'Aptos',max(size+.5,7.4),True)
                paragraph._element.append(build_equation(equation.group(1)))
                pos=equation.end()
            after=line[pos:]
            if after:
                run=paragraph.add_run(after)
                app_module.set_run_font(run,'Arial' if rtl else 'Aptos',max(size+.5,7.4),True)
    app_module.set_cell_text=set_cell_text
