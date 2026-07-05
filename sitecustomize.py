"""Application bootstrap hooks loaded automatically by Python's site module."""

try:
    import lesson_engine
    import lesson_runtime_patch

    if not getattr(lesson_engine, "_professional_runtime_installed", False):
        lesson_runtime_patch.install(lesson_engine)
        lesson_engine._professional_runtime_installed = True
except Exception:
    # The application still starts if optional bootstrap work cannot be loaded.
    pass
