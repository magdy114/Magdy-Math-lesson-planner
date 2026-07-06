# Render entrypoint for the expert lesson-planning and Word-export engines.
import app as core
import lesson_engine
import word_engine
import curriculum_runtime_patch
import curriculum_professional_patch
import curriculum_professional_hotfix
import lesson_density_patch
import lesson_speed_patch

# Use the official lesson-plan template stored in the main assets folder.
core.TEMPLATE_PATH = core.BASE_DIR / "assets" / "Lesson_Plan_Template_AY2026_2027.docx"

# Increase lesson-plan detail while preserving the official lesson template.
lesson_density_patch.install(lesson_engine)


def content_for(lesson):
    return lesson_engine.build_expert_content(lesson, core)


vars(core).update({"build_content": content_for})
word_engine.install_word_upgrade(core)

# Install the final curriculum pipeline in order: compatibility, professional
# grounded generation, then Arabic/font/image hardening.
curriculum_runtime_patch.install(core)
curriculum_professional_patch.install(core)
curriculum_professional_hotfix.install(core)

# Keep lesson generation responsive on Render: bounded AI timeout, no retries,
# and parallel Word creation for multi-lesson batches.
lesson_speed_patch.install(core, lesson_engine)

app = core.app
