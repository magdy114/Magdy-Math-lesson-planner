import app as core
import lesson_engine
import word_engine
import curriculum_runtime_patch
import curriculum_professional_patch
import curriculum_professional_hotfix
import lesson_density_patch
import subject_adaptive_patch
import lesson_speed_patch
import lesson_ui_speed_patch
import lesson_concurrency_patch
import scalable_runtime_patch
import lesson_source_grounding_patch
import lesson_upload_relevance_patch

core.TEMPLATE_PATH = core.BASE_DIR / "assets" / "Lesson_Plan_Template_AY2026_2027.docx"
lesson_density_patch.install(lesson_engine)
subject_adaptive_patch.install(core, lesson_engine, lesson_density_patch)


def content_for(lesson):
    return lesson_engine.build_expert_content(lesson, core)


vars(core).update({"build_content": content_for})
word_engine.install_word_upgrade(core)
curriculum_runtime_patch.install(core)
curriculum_professional_patch.install(core)
curriculum_professional_hotfix.install(core)
lesson_speed_patch.install(core, lesson_engine)
lesson_concurrency_patch.install(core)
scalable_runtime_patch.install(core, lesson_engine)
lesson_source_grounding_patch.install(core, lesson_engine, lesson_density_patch)
lesson_upload_relevance_patch.install(core)
lesson_ui_speed_patch.install(core.app)
app = core.app
