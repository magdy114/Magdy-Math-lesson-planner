from __future__ import annotations


def math_topic_family(topic: str, source_text: str = "", subject: str = "") -> str:
    text = f"{topic or ''} {source_text or ''}".lower()
    if any(word in text for word in ("مشتق", "اشتق", "derivative", "differentiation", "tangent", "مماس", "rate of change")):
        return "derivatives"
    if any(word in text for word in ("نها", "limit", "continuity", "اتصال", "approach")):
        return "limits"
    if any(word in text for word in ("تكامل", "integral", "area under", "definite", "antiderivative", "arc length", "طول المنحنى")):
        return "integrals"
    if any(word in text for word in ("لوغ", "log", "exponential", "أسي", "أسية", "ln", "growth", "decay")):
        return "logs"
    if any(word in text for word in ("مثلث", "trig", "sine", "cos", "tan", "جيب", "جا", "جتا", "radian", "unit circle")):
        return "trig"
    if any(word in text for word in ("دالة", "دوال", "function", "inverse", "composition", "domain", "range", "asymptote", "تقارب")):
        return "functions"
    if any(word in text for word in ("matrix", "مصفوف", "determinant", "cramer")):
        return "matrices"
    if any(word in text for word in ("vector", "متجه", "dot product", "cross product")):
        return "vectors"
    return "general"


def install(core) -> None:
    if getattr(core, "_lesson_math_family_hotfix_installed", False):
        return
    core.topic_family = math_topic_family
    core._lesson_math_family_hotfix_installed = True
