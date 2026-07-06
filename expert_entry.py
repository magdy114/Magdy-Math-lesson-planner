# Render entrypoint for the expert lesson-planning and Word-export engines.
import app as core
import lesson_engine
import word_engine
import curriculum_runtime_patch
import curriculum_professional_patch
import lesson_density_patch

# Use the official lesson-plan template stored in the main assets folder.
core.TEMPLATE_PATH = core.BASE_DIR / "assets" / "Lesson_Plan_Template_AY2026_2027.docx"

# Increase lesson-plan detail while preserving the official lesson template.
lesson_density_patch.install(lesson_engine)


def content_for(lesson):
    return lesson_engine.build_expert_content(lesson, core)


vars(core).update({"build_content": content_for})
word_engine.install_word_upgrade(core)

# Preserve image/file compatibility, then install the grounded professional
# curriculum engine as the final authority for extraction and MTP generation.
curriculum_runtime_patch.install(core)
curriculum_professional_patch.install(core)

app = core.app
