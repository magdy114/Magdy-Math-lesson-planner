from __future__ import annotations

import re
from typing import Any

EQ_RE = re.compile(r"\[\[EQ:(.+?)\]\]")
MATH_SECTIONS = ("starter", "main", "teacher_led", "student_led", "plenary", "kpi")


def _matching(text: str, start: int, opening: str = "(", closing: str = ")") -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    start = 0
    round_depth = curly_depth = 0
    for index, char in enumerate(text):
        if char == "(":
            round_depth += 1
        elif char == ")":
            round_depth -= 1
        elif char == "{":
            curly_depth += 1
        elif char == "}":
            curly_depth -= 1
        elif char == "," and round_depth == 0 and curly_depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    args.append(text[start:].strip())
    return args


def _balanced(text: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for char in text:
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return False
    return not stack


def _operand_left(text: str, slash: int) -> tuple[int, str] | None:
    index = slash - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    if index < 0:
        return None
    if text[index] == ")":
        depth = 0
        for cursor in range(index, -1, -1):
            if text[cursor] == ")":
                depth += 1
            elif text[cursor] == "(":
                depth -= 1
                if depth == 0:
                    start = cursor
                    name_cursor = start - 1
                    while name_cursor >= 0 and (text[name_cursor].isalnum() or text[name_cursor] in "_′'"):
                        name_cursor -= 1
                    if name_cursor < start - 1:
                        start = name_cursor + 1
                    return start, text[start:index + 1]
        return None
    start = index
    while start >= 0 and (text[start].isalnum() or text[start] in "._^'′"):
        start -= 1
    start += 1
    return (start, text[start:index + 1]) if start <= index else None


def _operand_right(text: str, slash: int) -> tuple[int, str] | None:
    index = slash + 1
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return None
    if text[index] == "(":
        end = _matching(text, index)
        return (end + 1, text[index:end + 1]) if end >= 0 else None
    start = index
    while index < len(text) and (text[index].isalnum() or text[index] in "._^'′"):
        index += 1
    if index < len(text) and text[index] == "(":
        end = _matching(text, index)
        if end >= 0:
            index = end + 1
    return (index, text[start:index]) if index > start else None


def _slash_to_frac(expression: str) -> str:
    text = expression
    for _ in range(12):
        slash = text.find("/")
        if slash < 0:
            break
        left = _operand_left(text, slash)
        right = _operand_right(text, slash)
        if not left or not right:
            break
        left_start, numerator = left
        right_end, denominator = right
        numerator = numerator[1:-1] if numerator.startswith("(") and numerator.endswith(")") else numerator
        denominator = denominator[1:-1] if denominator.startswith("(") and denominator.endswith(")") else denominator
        text = text[:left_start] + f"frac({numerator},{denominator})" + text[right_end:]
    return text


def _normalise_equation(expression: str) -> str:
    text = str(expression or "").strip()
    text = text.replace("**", "^").replace("×", "*").replace("÷", "/")
    text = text.replace("√", "sqrt")
    text = re.sub(r"sqrt\s+([A-Za-z0-9]+)", r"sqrt(\1)", text)
    text = re.sub(r"(?<=\d)(?=sqrt\()", "*", text)
    text = re.sub(r"(?<=\))(?=sqrt\()", "*", text)
    text = _slash_to_frac(text)
    return re.sub(r"\s+", " ", text)


def _replace_custom_functions(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        matched = None
        for name in ("frac", "sqrt", "lim", "int", "sum"):
            if text.startswith(name + "(", index):
                matched = name
                break
        if matched is None:
            output.append(text[index])
            index += 1
            continue
        open_index = index + len(matched)
        close_index = _matching(text, open_index)
        if close_index < 0:
            output.append(text[index])
            index += 1
            continue
        args = [_replace_custom_functions(arg) for arg in _split_args(text[open_index + 1:close_index])]
        if matched == "frac" and len(args) >= 2:
            replacement = f"(({args[0]})/({args[1]}))"
        elif matched == "sqrt" and args:
            replacement = f"sqrt({args[0]})"
        elif matched == "lim" and len(args) >= 3:
            replacement = f"Limit(({args[2]}),{args[0]},({args[1]}))"
        elif matched == "int" and len(args) >= 3:
            variable = re.sub(r"^d", "", args[3]) if len(args) > 3 else "x"
            replacement = f"Integral(({args[2]}),({variable},({args[0]}),({args[1]})))"
        elif matched == "sum" and len(args) >= 3:
            replacement = f"Sum(({args[2]}),(n,({args[0]}),({args[1]})))"
        else:
            replacement = text[index:close_index + 1]
        output.append(replacement)
        index = close_index + 1
    return "".join(output)


def _top_level_equals(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "=" and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _sympy_tools():
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import (
            convert_xor,
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
        transformations = standard_transformations + (implicit_multiplication_application, convert_xor)
        return sp, parse_expr, transformations
    except Exception:
        return None, None, None


def _expand_defined_functions(text: str, definitions: dict[str, Any], sp) -> str:
    value = text
    for name, expression in definitions.items():
        if len(name) != 1 or not name.isalpha():
            continue
        pattern = re.compile(rf"\b{re.escape(name)}\(([^()]*)\)")
        for _ in range(4):
            match = pattern.search(value)
            if not match:
                break
            argument = match.group(1)
            try:
                replacement = str(expression.subs(sp.Symbol("x"), sp.sympify(argument)))
            except Exception:
                replacement = f"({expression})"
            value = value[:match.start()] + f"({replacement})" + value[match.end():]
    return value


def _parse_term(text: str, definitions: dict[str, Any]):
    sp, parse_expr, transformations = _sympy_tools()
    if sp is None:
        return None
    raw = _normalise_equation(text)
    derivative = re.fullmatch(r"([A-Za-z])['′](?:\(([^)]+)\))?", raw)
    if derivative:
        name, point = derivative.groups()
        if name not in definitions:
            return None
        result = sp.diff(definitions[name], sp.Symbol("x"))
        if point:
            try:
                point_expr = parse_expr(_replace_custom_functions(point), transformations=transformations, evaluate=True)
                result = result.subs(sp.Symbol("x"), point_expr)
            except Exception:
                return None
        return result

    raw = _expand_defined_functions(raw, definitions, sp)
    converted = _replace_custom_functions(raw).replace("^", "**")
    local_dict = {
        "sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "ln": sp.log, "log": sp.log, "exp": sp.exp,
        "Limit": sp.Limit, "Integral": sp.Integral, "Sum": sp.Sum,
        "pi": sp.pi, "e": sp.E,
    }
    try:
        result = parse_expr(converted, local_dict=local_dict, transformations=transformations, evaluate=True)
        if isinstance(result, (sp.Limit, sp.Integral, sp.Sum)):
            result = result.doit()
        return result
    except Exception:
        return None


def _record_definition(left: str, right: str, definitions: dict[str, Any]) -> bool:
    function_match = re.fullmatch(r"([A-Za-z])\(x\)", left.strip())
    symbol_match = re.fullmatch(r"([uvy])", left.strip())
    if not function_match and not symbol_match:
        return False
    name = (function_match or symbol_match).group(1)
    parsed = _parse_term(right, definitions)
    if parsed is not None:
        definitions[name] = parsed
    return True


def _validate_equation(expression: str, definitions: dict[str, Any]) -> tuple[bool | None, str]:
    normal = _normalise_equation(expression)
    if not normal or not _balanced(normal):
        return False, normal
    parts = _top_level_equals(normal)
    if len(parts) == 1:
        return None, normal

    if len(parts) == 2 and _record_definition(parts[0], parts[1], definitions):
        return None, normal

    if len(parts) == 2 and re.fullmatch(r"[A-Za-z]", parts[0]):
        return None, normal

    # In a chain such as m=f'(2)=4, the first symbol is a label/assignment.
    compare_parts = parts[1:] if len(parts) > 2 and re.fullmatch(r"[A-Za-z]", parts[0]) else parts
    evaluated = [_parse_term(part, definitions) for part in compare_parts]
    if any(item is None for item in evaluated):
        return None, normal

    sp, _, _ = _sympy_tools()
    try:
        for left, right in zip(evaluated, evaluated[1:]):
            if sp.simplify(left - right) != 0:
                return False, normal
        return True, normal
    except Exception:
        return None, normal


def _repair_section(value: str, fallback: str) -> tuple[str, int, int]:
    definitions: dict[str, Any] = {}
    valid_count = invalid_count = 0
    repaired = value
    replacements: dict[str, str] = {}
    for match in EQ_RE.finditer(value):
        raw = match.group(1).strip()
        status, normal = _validate_equation(raw, definitions)
        if status is False:
            invalid_count += 1
        elif status is True:
            valid_count += 1
        replacements[raw] = normal

    if invalid_count:
        return fallback or value, valid_count, invalid_count

    for raw, normal in replacements.items():
        repaired = repaired.replace(f"[[EQ:{raw}]]", f"[[EQ:{normal}]]")
    return repaired, valid_count, invalid_count


def install(lesson_engine) -> None:
    original_build = lesson_engine.build_expert_content

    def guarded_build(lesson, app):
        output = original_build(lesson, app)
        if lesson_engine.family(lesson.subject) != "math":
            return output

        fallback = lesson_engine.special(lesson, app)
        try:
            import lesson_runtime_patch
            fallback = lesson_runtime_patch._postprocess(lesson, fallback, fallback)
        except Exception:
            pass

        checked = dict(output)
        valid_total = invalid_total = 0
        for key in MATH_SECTIONS:
            value = str(checked.get(key, ""))
            fallback_value = str(fallback.get(key, ""))
            repaired, valid, invalid = _repair_section(value, fallback_value)
            checked[key] = repaired
            valid_total += valid
            invalid_total += invalid
        checked["_math_qa"] = f"validated:{valid_total};replaced:{invalid_total}"
        if invalid_total:
            checked["_mode"] = str(checked.get("_mode", "ai")) + "+math_guard"
        return checked

    lesson_engine.build_expert_content = guarded_build
