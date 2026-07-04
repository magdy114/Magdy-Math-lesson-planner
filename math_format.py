from docx.oxml import OxmlElement

def make_math_run(text):
    return OxmlElement('m:r')
