# Render entrypoint for the expert lesson-planning and Word-export engines.
import app as core
import lesson_engine
import word_engine

def content_for(lesson):
    return lesson_engine.build_expert_content(lesson,core)

vars(core).update({'build_content':content_for})
word_engine.install_word_upgrade(core)
app=core.app
