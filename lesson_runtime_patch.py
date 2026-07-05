from __future__ import annotations

import re

ALLOWED_ARABIC_ACRONYMS = {
    "SDG", "STEM", "AFL", "KPI", "IEP", "APL", "ICT", "AI", "GeoGebra", "Desmos"
}

ARABIC_REPLACEMENTS = {
    "HOTS": "سؤال تفكير عليا",
    "Exit Ticket": "بطاقة خروج",
    "exit ticket": "بطاقة خروج",
    "Think-Pair-Share": "فكر–زاوج–شارك",
    "Think Pair Share": "فكر–زاوج–شارك",
    "Teacher-led": "دور المعلم",
    "Student-led": "دور الطلاب",
    "Worked Example": "مثال محلول",
    "Guided Practice": "تدريب موجه",
    "Independent Practice": "تطبيق فردي",
    "Expected response": "الاستجابة المتوقعة",
    "Diagnostic question": "سؤال تشخيصي",
    "Hook": "تمهيد",
}

MATH_FUNCTIONS = ("frac", "sqrt", "lim", "int", "sum")


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _normalise_equation_code(code: str) -> str:
    code = str(code or "").strip()
    code = code.replace("**", "^")
    code = code.replace("×", "*").replace("÷", "/")
    code = re.sub(r"(?<=\d)(?=sqrt\s*\()", "*", code)
    code = re.sub(r"(?<=\))(?=sqrt\s*\()", "*", code)
    code = re.sub(r"\s+", " ", code)
    return code


def _wrap_raw_math_functions(text: str) -> str:
    """Wrap raw frac/sqrt/lim/int/sum calls in Word-equation markers.

    This prevents expressions such as frac(1,2sqrt(x)) from being printed as
    ordinary text inside Arabic sentences.
    """
    result: list[str] = []
    index = 0
    inside_marker = False
    while index < len(text):
        if text.startswith("[[EQ:", index):
            end = text.find("]]", index + 5)
            if end == -1:
                result.append(text[index:])
                break
            code = _normalise_equation_code(text[index + 5:end])
            result.append(f"[[EQ:{code}]]")
            index = end + 2
            continue

        found = None
        for name in MATH_FUNCTIONS:
            token = name + "("
            if text.startswith(token, index):
                found = name
                break
        if found is None:
            result.append(text[index])
            index += 1
            continue

        open_index = index + len(found)
        close_index = _matching_paren(text, open_index)
        if close_index < 0:
            result.append(text[index])
            index += 1
            continue
        code = _normalise_equation_code(text[index:close_index + 1])
        result.append(f"[[EQ:{code}]]")
        index = close_index + 1
    return "".join(result)


def _wrap_equation_lines(text: str) -> str:
    lines: list[str] = []
    equation_line = re.compile(
        r"^\s*(?:[A-Za-z][A-Za-z0-9]*\s*(?:\([^)]*\))?\s*[=≈<>≤≥]|"
        r"(?:u|v|y|f|g|h|p|q|r)(?:['′]{1,2})?\s*=).+$"
    )
    for raw in str(text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if line and "[[EQ:" not in line and equation_line.match(line):
            line = f"[[EQ:{_normalise_equation_code(line)}]]"
        lines.append(_wrap_raw_math_functions(line))
    return "\n".join(lines)


def _arabic_cleanup(text: str) -> str:
    value = str(text or "")
    for source, target in ARABIC_REPLACEMENTS.items():
        value = value.replace(source, target)
    value = value.replace("Group 1", "المجموعة الأولى")
    value = value.replace("Group 2", "المجموعة الثانية")
    value = value.replace("Group 3", "المجموعة الثالثة")
    value = value.replace("Group 4", "المجموعة الرابعة")
    return value


def _latin_words(text: str) -> list[str]:
    return re.findall(r"\b[A-Za-z][A-Za-z-]{2,}\b", str(text or ""))


def _language_contaminated(value: str, language: str) -> bool:
    if language == "ar":
        words = [word for word in _latin_words(value) if word not in ALLOWED_ARABIC_ACRONYMS]
        # Mathematical function names live inside equation markers and are acceptable.
        cleaned = re.sub(r"\[\[EQ:.*?\]\]", "", value, flags=re.S)
        words = [word for word in _latin_words(cleaned) if word not in ALLOWED_ARABIC_ACRONYMS]
        return len(words) >= 5
    return len(re.findall(r"[\u0600-\u06ff]", value)) >= 8


def _postprocess(lesson, result: dict, fallback: dict) -> dict:
    language = lesson.language
    output = dict(result or {})
    for key, value in list(output.items()):
        if key.startswith("_") or not isinstance(value, str):
            continue
        cleaned = _arabic_cleanup(value) if language == "ar" else value
        cleaned = _wrap_equation_lines(cleaned)
        if _language_contaminated(cleaned, language) and key in fallback:
            cleaned = _wrap_equation_lines(
                _arabic_cleanup(fallback[key]) if language == "ar" else fallback[key]
            )
        output[key] = cleaned.strip()
    return output


def install(lesson_engine) -> None:
    original_build = lesson_engine.build_expert_content
    original_prompt = lesson_engine.system_prompt

    def professional_prompt(language: str) -> str:
        base = original_prompt(language)
        if language == "ar":
            return base + (
                "\nالتزم بالعربية فقط، ولا تستخدم كلمات إنجليزية إلا الاختصارات الرسمية SDG وSTEM وAFL وKPI وIEP/APL "
                "وأسماء الأدوات GeoGebra وDesmos. استبدل HOTS بعبارة سؤال تفكير عليا وExit Ticket ببطاقة خروج. "
                "اكتب كل تعبير رياضي داخل [[EQ:...]] حصراً. لا تكتب frac أو sqrt أو lim أو int كنص عادي. "
                "استخدم أمثلة رياضية صحيحة، وتأكد أن المشتقات والكسور والجذور متسقة حسابياً قبل الإخراج."
            )
        return base + (
            "\nUse English only. Put every mathematical expression inside [[EQ:...]]. Never print frac, sqrt, lim, "
            "or int as ordinary text. Verify worked examples and guided-practice expressions before output."
        )

    def build(lesson, app):
        result = original_build(lesson, app)
        fallback = lesson_engine.special(lesson, app)
        return _postprocess(lesson, result, fallback)

    lesson_engine.system_prompt = professional_prompt
    lesson_engine.build_expert_content = build
