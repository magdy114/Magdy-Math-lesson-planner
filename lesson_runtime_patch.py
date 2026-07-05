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
    "Independent Application": "تطبيق فردي",
    "Expected response": "الاستجابة المتوقعة",
    "Diagnostic question": "سؤال تشخيصي",
    "Learning evidence": "دليل التعلم",
    "Success measure": "مؤشر النجاح",
    "Misconception": "خطأ متوقع",
    "Hook": "تمهيد",
}

MATH_FUNCTIONS = ("frac", "sqrt", "lim", "int", "sum")

SECTION_LIMITS = {
    "keywords": (4, 420),
    "sdg": (5, 650),
    "strategies": (7, 950),
    "intervention": (7, 950),
    "learning_outcomes": (6, 1200),
    "differentiation": (8, 1250),
    "success_criteria": (6, 1100),
    "starter": (6, 1000),
    "main": (15, 2400),
    "teacher_led": (8, 1300),
    "student_led": (8, 1300),
    "plenary": (7, 1050),
    "kpi": (7, 1000),
    "resources": (6, 800),
    "curriculum": (6, 850),
}

REQUIRED_HEADINGS_AR = {
    "starter": ("تمهيد", "سؤال تشخيصي", "الاستجابة المتوقعة"),
    "main": ("مثال محلول", "تدريب موجه", "تطبيق فردي", "سؤال تفكير عليا"),
    "teacher_led": ("دور المعلم", "أسئلة التحقق", "التغذية الراجعة"),
    "student_led": ("دور الطلاب", "المنتج المتوقع", "دليل التعلم"),
    "plenary": ("بطاقة خروج", "سؤال تحقق", "تأمل ذاتي"),
    "differentiation": ("دعم", "المستوى المتوقع", "متقدمون", "IEP/APL"),
}

REQUIRED_HEADINGS_EN = {
    "starter": ("Hook", "Diagnostic Question", "Expected Response"),
    "main": ("Worked Example", "Guided Practice", "Independent Practice", "HOTS"),
    "teacher_led": ("Teacher Role", "Checks for Understanding", "Feedback"),
    "student_led": ("Student Role", "Expected Product", "Learning Evidence"),
    "plenary": ("Exit Ticket", "Check Question", "Self-Reflection"),
    "differentiation": ("Support", "Expected Level", "Advanced", "IEP/APL"),
}


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
    result: list[str] = []
    index = 0
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
    value = value.replace("group 1", "المجموعة الأولى")
    value = value.replace("group 2", "المجموعة الثانية")
    value = value.replace("group 3", "المجموعة الثالثة")
    value = value.replace("group 4", "المجموعة الرابعة")
    return value


def _latin_words(text: str) -> list[str]:
    return re.findall(r"\b[A-Za-z][A-Za-z-]{2,}\b", str(text or ""))


def _language_contaminated(value: str, language: str) -> bool:
    if language == "ar":
        cleaned = re.sub(r"\[\[EQ:.*?\]\]", "", value, flags=re.S)
        words = [word for word in _latin_words(cleaned) if word not in ALLOWED_ARABIC_ACRONYMS]
        return len(words) >= 4
    return len(re.findall(r"[\u0600-\u06ff]", value)) >= 6


def _clean_lines(value: str) -> list[str]:
    text = str(value or "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    output: list[str] = []
    previous = ""
    for raw in text.split("\n"):
        line = raw.strip(" \t•-–—")
        if not line:
            continue
        signature = re.sub(r"\W+", "", line.casefold())
        if signature and signature == previous:
            continue
        previous = signature
        output.append(line)
    return output


def _split_dense_line(value: str, target_lines: int) -> list[str]:
    lines = _clean_lines(value)
    if len(lines) > 1:
        return lines
    if not lines:
        return []
    text = lines[0]
    pieces = re.split(r"(?<=[.!؟؛])\s+|\s+(?=\d+[.)])", text)
    pieces = [piece.strip() for piece in pieces if piece.strip()]
    return pieces if len(pieces) >= 2 else lines


def _number_lines(value: str, count: int) -> str:
    lines = _split_dense_line(value, count)
    numbered: list[str] = []
    for line in lines:
        line = re.sub(r"^\d+[.)-]?\s*", "", line).strip()
        if line:
            numbered.append(line)
        if len(numbered) >= count:
            break
    return "\n".join(f"{index}. {line}" for index, line in enumerate(numbered, 1))


def _has_heading(lines: list[str], heading: str) -> bool:
    target = heading.casefold()
    return any(line.casefold().startswith(target + ":") or line.casefold() == target for line in lines)


def _structure_section(key: str, value: str, language: str, fallback: str) -> str:
    if key in {"learning_outcomes", "success_criteria"}:
        numbered = _number_lines(value, 6)
        if len(_clean_lines(numbered)) < 4:
            numbered = _number_lines(fallback, 6)
        return numbered

    headings_map = REQUIRED_HEADINGS_AR if language == "ar" else REQUIRED_HEADINGS_EN
    headings = headings_map.get(key)
    if not headings:
        return "\n".join(_clean_lines(value))

    lines = _split_dense_line(value, len(headings))
    if not lines:
        lines = _split_dense_line(fallback, len(headings))

    result: list[str] = []
    source_index = 0
    for heading in headings:
        if _has_heading(lines, heading):
            for line in lines:
                if line.casefold().startswith(heading.casefold()):
                    result.append(line)
                    break
            continue
        while source_index < len(lines) and ":" in lines[source_index] and len(lines[source_index].split(":", 1)[0]) < 38:
            source_index += 1
        body = lines[source_index] if source_index < len(lines) else ""
        source_index += 1
        if body:
            result.append(f"{heading}: {body}")

    for line in lines:
        if line not in result and len(result) < len(headings) + 3:
            result.append(line)
    return "\n".join(result)


def _limit_section(key: str, value: str) -> str:
    max_lines, max_chars = SECTION_LIMITS.get(key, (12, 1800))
    lines = _clean_lines(value)[:max_lines]
    output: list[str] = []
    current = 0
    for line in lines:
        addition = len(line) + (1 if output else 0)
        if current + addition > max_chars:
            remaining = max_chars - current
            if remaining > 60:
                output.append(line[:remaining].rstrip(" ،,;؛:") + "…")
            break
        output.append(line)
        current += addition
    return "\n".join(output)


def _postprocess(lesson, result: dict, fallback: dict) -> dict:
    language = lesson.language
    output = dict(result or {})
    for key, value in list(output.items()):
        if key.startswith("_") or not isinstance(value, str):
            continue
        fallback_value = str(fallback.get(key, ""))
        cleaned = _arabic_cleanup(value) if language == "ar" else value
        if _language_contaminated(cleaned, language) and fallback_value:
            cleaned = _arabic_cleanup(fallback_value) if language == "ar" else fallback_value
        cleaned = _structure_section(key, cleaned, language, fallback_value)
        cleaned = _wrap_equation_lines(cleaned)
        cleaned = _limit_section(key, cleaned)
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
                "اكتب كل تعبير رياضي داخل [[EQ:...]] حصراً، ولا تكتب frac أو sqrt أو lim أو int كنص عادي. "
                "استخدم أمثلة رياضية صحيحة وتحقق من المشتقات والكسور والجذور قبل الإخراج. "
                "اكتب 6 نواتج تعلم مرقمة و6 معايير نجاح مرقمة. اجعل التمهيد من ثلاثة أسطر معنونة: تمهيد، سؤال تشخيصي، الاستجابة المتوقعة. "
                "نظم الأنشطة الرئيسة إلى: مثال محلول، تدريب موجه، تطبيق فردي، سؤال تفكير عليا. "
                "نظم التمايز إلى: دعم، المستوى المتوقع، متقدمون، IEP/APL. لا تكرر الفكرة نفسها، ولا تكتب فقرات طويلة غير معنونة."
            )
        return base + (
            "\nUse English only. Put every mathematical expression inside [[EQ:...]]. Never print frac, sqrt, lim, "
            "or int as ordinary text. Verify all worked examples. Provide exactly six numbered learning outcomes and six numbered success criteria. "
            "Structure Starter as Hook, Diagnostic Question, and Expected Response. Structure Main Activities as Worked Example, Guided Practice, "
            "Independent Practice, and HOTS. Structure differentiation as Support, Expected Level, Advanced, and IEP/APL. Avoid repetition and long unlabelled paragraphs."
        )

    def build(lesson, app):
        result = original_build(lesson, app)
        fallback = lesson_engine.special(lesson, app)
        return _postprocess(lesson, result, fallback)

    lesson_engine.system_prompt = professional_prompt
    lesson_engine.build_expert_content = build
