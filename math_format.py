from __future__ import annotations

import re
from typing import List, Tuple

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

SUPERSCRIPT_TRANSLATION = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
})


def math_run(text: str, plain: bool = False):
    run = OxmlElement("m:r")
    run_properties = OxmlElement("m:rPr")
    style = OxmlElement("m:sty")
    style.set(qn("m:val"), "p" if plain else "i")
    run_properties.append(style)
    run.append(run_properties)
    token = OxmlElement("m:t")
    token.text = text
    run.append(token)
    return run


def split_args(text: str) -> List[str]:
    args: list[str] = []
    depth_round = depth_curly = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth_round += 1
        elif char == ")":
            depth_round -= 1
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
        elif char == "," and depth_round == 0 and depth_curly == 0:
            args.append(text[start:index].strip())
            start = index + 1
    args.append(text[start:].strip())
    return args


def matching_paren(text: str, start: int, opening: str = "(", closing: str = ")") -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return len(text) - 1


def _normalise(expression: str) -> str:
    text = str(expression or "").strip()
    text = text.replace("**", "^")
    text = text.replace("−", "-").replace("×", "*").replace("÷", "/")
    text = text.replace("≤", "<=").replace("≥", ">=").replace("≠", "!=")
    text = text.replace("→", "->")
    text = re.sub(r"√\s*\(([^()]*)\)", r"sqrt(\1)", text)
    text = re.sub(r"√\s*([A-Za-z0-9]+)", r"sqrt(\1)", text)
    text = re.sub(r"(?<=\d)(?=sqrt\s*\()", "*", text)
    text = re.sub(r"(?<=\))(?=sqrt\s*\()", "*", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _append_expression(container, expression: str) -> None:
    for node in parse_math(expression):
        container.append(node)


def make_fraction(numerator: str, denominator: str):
    fraction = OxmlElement("m:f")
    numerator_node = OxmlElement("m:num")
    denominator_node = OxmlElement("m:den")
    _append_expression(numerator_node, numerator)
    _append_expression(denominator_node, denominator)
    fraction.extend([numerator_node, denominator_node])
    return fraction


def make_radical(expression: str):
    radical = OxmlElement("m:rad")
    properties = OxmlElement("m:radPr")
    degree_hidden = OxmlElement("m:degHide")
    degree_hidden.set(qn("m:val"), "1")
    properties.append(degree_hidden)
    radical.append(properties)
    radical.append(OxmlElement("m:deg"))
    element = OxmlElement("m:e")
    _append_expression(element, expression)
    radical.append(element)
    return radical


def make_script(base: List, subscript: str | None = None, superscript: str | None = None):
    if subscript is not None and superscript is not None:
        element = OxmlElement("m:sSubSup")
        base_node = OxmlElement("m:e")
        sub_node = OxmlElement("m:sub")
        sup_node = OxmlElement("m:sup")
        for node in base:
            base_node.append(node)
        _append_expression(sub_node, subscript)
        _append_expression(sup_node, superscript)
        element.extend([base_node, sub_node, sup_node])
        return element

    element = OxmlElement("m:sSub" if subscript is not None else "m:sSup")
    base_node = OxmlElement("m:e")
    script_node = OxmlElement("m:sub" if subscript is not None else "m:sup")
    for node in base:
        base_node.append(node)
    _append_expression(script_node, subscript if subscript is not None else superscript or "")
    element.extend([base_node, script_node])
    return element


def make_integral(lower: str, upper: str, expression: str, differential: str):
    integral = OxmlElement("m:nary")
    properties = OxmlElement("m:naryPr")
    character = OxmlElement("m:chr")
    character.set(qn("m:val"), "∫")
    limit_location = OxmlElement("m:limLoc")
    limit_location.set(qn("m:val"), "subSup")
    grow = OxmlElement("m:grow")
    grow.set(qn("m:val"), "1")
    properties.extend([character, limit_location, grow])
    integral.append(properties)

    sub_node = OxmlElement("m:sub")
    sup_node = OxmlElement("m:sup")
    expression_node = OxmlElement("m:e")
    _append_expression(sub_node, lower)
    _append_expression(sup_node, upper)
    _append_expression(expression_node, expression)
    if differential:
        expression_node.append(math_run(" " + differential, plain=True))
    integral.extend([sub_node, sup_node, expression_node])
    return integral


def make_sum(lower: str, upper: str, expression: str):
    summation = OxmlElement("m:nary")
    properties = OxmlElement("m:naryPr")
    character = OxmlElement("m:chr")
    character.set(qn("m:val"), "∑")
    location = OxmlElement("m:limLoc")
    location.set(qn("m:val"), "subSup")
    properties.extend([character, location])
    summation.append(properties)
    sub_node = OxmlElement("m:sub")
    sup_node = OxmlElement("m:sup")
    expression_node = OxmlElement("m:e")
    _append_expression(sub_node, lower)
    _append_expression(sup_node, upper)
    _append_expression(expression_node, expression)
    summation.extend([sub_node, sup_node, expression_node])
    return summation


def make_limit(variable: str, target: str, expression: str):
    limit = OxmlElement("m:limLow")
    base = OxmlElement("m:e")
    base.append(math_run("lim", plain=True))
    lower = OxmlElement("m:lim")
    _append_expression(lower, f"{variable}->{target}")
    limit.extend([base, lower])
    return [limit, math_run(" ", plain=True)] + parse_math(expression)


def read_script(text: str, index: int) -> Tuple[str, int]:
    if index >= len(text):
        return "", index
    if text[index] == "(":
        end = matching_paren(text, index)
        return text[index + 1:end], end + 1
    if text[index] == "{":
        end = matching_paren(text, index, "{", "}")
        return text[index + 1:end], end + 1
    match = re.match(r"[A-Za-z0-9π∞θ]+", text[index:])
    if match:
        value = match.group(0)
        return value, index + len(value)
    return text[index:index + 1], index + 1


def _group(nodes: List):
    box = OxmlElement("m:box")
    expression = OxmlElement("m:e")
    for node in nodes:
        expression.append(node)
    box.append(expression)
    return box


def _top_level_slash(text: str) -> int:
    depth_round = depth_curly = 0
    slash = -1
    for index, char in enumerate(text):
        if char == "(":
            depth_round += 1
        elif char == ")":
            depth_round -= 1
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
        elif char == "/" and depth_round == 0 and depth_curly == 0:
            if slash != -1:
                return -1
            slash = index
    return slash


def _apply_scripts(base: List, text: str, index: int):
    subscript = superscript = None
    while index < len(text) and text[index] in "^_":
        kind = text[index]
        value, index = read_script(text, index + 1)
        if kind == "^":
            superscript = value
        else:
            subscript = value
    node = make_script(base, subscript, superscript) if subscript is not None or superscript is not None else (
        base[0] if len(base) == 1 else _group(base)
    )
    return node, index


def parse_math(expression: str) -> List:
    text = _normalise(expression)
    if not text:
        return []

    slash_index = _top_level_slash(text)
    if 0 < slash_index < len(text) - 1:
        return [make_fraction(text[:slash_index], text[slash_index + 1:])]

    nodes: list = []
    index = 0
    function_names = ("sqrt", "frac", "int", "lim", "sum")
    upright_names = ("sin", "cos", "tan", "sec", "csc", "cot", "ln", "log")

    while index < len(text):
        matched = False
        for name in function_names:
            prefix = name + "("
            if text.startswith(prefix, index):
                end = matching_paren(text, index + len(name))
                args = split_args(text[index + len(prefix):end])
                if name == "sqrt" and args:
                    nodes.append(make_radical(args[0]))
                elif name == "frac" and len(args) >= 2:
                    nodes.append(make_fraction(args[0], args[1]))
                elif name == "int" and len(args) >= 3:
                    nodes.append(make_integral(args[0], args[1], args[2], args[3] if len(args) > 3 else "dx"))
                elif name == "lim" and len(args) >= 3:
                    nodes.extend(make_limit(args[0], args[1], args[2]))
                elif name == "sum" and len(args) >= 3:
                    nodes.append(make_sum(args[0], args[1], args[2]))
                index = end + 1
                matched = True
                break
        if matched:
            continue

        char = text[index]
        if char.isspace():
            nodes.append(math_run(" ", plain=True))
            index += 1
            continue

        if char == "(":
            end = matching_paren(text, index)
            base = [math_run("(", plain=True)] + parse_math(text[index + 1:end]) + [math_run(")", plain=True)]
            index = end + 1
            node, index = _apply_scripts(base, text, index)
            nodes.append(node)
            continue

        if char.isdigit():
            end = index + 1
            while end < len(text) and (text[end].isdigit() or text[end] == "."):
                end += 1
            base = [math_run(text[index:end], plain=True)]
            index = end
            node, index = _apply_scripts(base, text, index)
            nodes.append(node)
            continue

        if char.isalpha() or char in "π∞θ":
            end = index + 1
            while end < len(text) and (text[end].isalpha() or text[end] in "π∞θ"):
                end += 1
            name = text[index:end]
            # Keep named functions upright; variables remain italic.
            base = [math_run(name, plain=name in upright_names)]
            index = end
            # A prime belongs to the base before sub/superscripts.
            while index < len(text) and text[index] in "'′":
                base.append(math_run("′", plain=True))
                index += 1
            node, index = _apply_scripts(base, text, index)
            nodes.append(node)
            continue

        replacements = {
            "-": "−", "*": "·", "<=": "≤", ">=": "≥", "!=": "≠", "->": "→",
        }
        two = text[index:index + 2]
        if two in replacements:
            nodes.append(math_run(replacements[two], plain=True))
            index += 2
        else:
            nodes.append(math_run(replacements.get(char, char), plain=True))
            index += 1

    return nodes


def build_equation(expression: str):
    equation = OxmlElement("m:oMath")
    for node in parse_math(expression):
        equation.append(node)
    return equation
