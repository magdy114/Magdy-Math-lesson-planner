"""Lightweight startup hooks for the lesson planner."""

try:
    import lesson_engine
    import lesson_runtime_patch

    if not getattr(lesson_engine, "_professional_runtime_installed", False):
        lesson_runtime_patch.install(lesson_engine)
        lesson_engine._professional_runtime_installed = True
except Exception:
    pass

try:
    import lesson_engine
    import math_quality_guard

    if not getattr(lesson_engine, "_math_quality_guard_installed", False):
        math_quality_guard.install(lesson_engine)
        lesson_engine._math_quality_guard_installed = True
except Exception:
    pass
