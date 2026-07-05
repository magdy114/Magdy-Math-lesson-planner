"""Application bootstrap hooks loaded automatically by Python's site module."""

try:
    import lesson_engine
    import lesson_runtime_patch

    if not getattr(lesson_engine, "_professional_runtime_installed", False):
        lesson_runtime_patch.install(lesson_engine)
        lesson_engine._professional_runtime_installed = True
except Exception:
    pass

try:
    import word_engine
    import lesson_layout_patch

    if not getattr(word_engine, "_professional_layout_installed", False):
        lesson_layout_patch.install(word_engine)
        word_engine._professional_layout_installed = True
except Exception:
    pass
