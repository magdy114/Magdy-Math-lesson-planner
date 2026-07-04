# Render entrypoint for the expert lesson-planning and Word-export engines.
import app as core
import lesson_engine
import word_engine

# Use the newly uploaded template even though it was placed in assets/assets.
# This keeps the application working without asking the user to move the binary file again.
_nested_template = core.BASE_DIR / "assets" / "assets" / "Lesson_Plan_Template_AY2026_2027.docx"
_default_template = core.BASE_DIR / "assets" / "Lesson_Plan_Template_AY2026_2027.docx"
core.TEMPLATE_PATH = _nested_template if _nested_template.exists() else _default_template

def content_for(lesson):
    return lesson_engine.build_expert_content(lesson, core)

vars(core).update({'build_content': content_for})
word_engine.install_word_upgrade(core)
app = core.app
