from __future__ import annotations

import re

NUMBER_RE = re.compile(r"^\s*[\u200e\u200f]*(\d+)[\.)-]?\s*(.*)$")
EQ_RE = re.compile(r"\[\[EQ:.*?\]\]")


def _lines(value: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").replace("\r", "").split("\n"):
        line = re.sub(r"\s+", " ", raw).strip(" •–—-")
        if not line:
            continue
        signature = re.sub(r"[^\w\u0600-\u06ff]+", "", line.casefold())
        if signature and signature not in seen:
            seen.add(signature)
            output.append(line)
    return output


def _body(line: str) -> str:
    match = NUMBER_RE.match(line)
    return (match.group(2) if match else line).strip()


def _word_count(text: str) -> int:
    plain = EQ_RE.sub("", text)
    return len(re.findall(r"[\w\u0600-\u06ff]+", plain))


def _ensure_sentence(text: str) -> str:
    value = text.strip()
    if value and value[-1] not in ".؟!":
        value += "."
    return value


def _extend_ar(text: str, suffix: str, minimum_words: int) -> str:
    value = _ensure_sentence(text)
    if _word_count(value) < minimum_words:
        value = value.rstrip(".") + "، " + suffix
        value = _ensure_sentence(value)
    return value


def _extend_en(text: str, suffix: str, minimum_words: int) -> str:
    value = _ensure_sentence(text)
    if _word_count(value) < minimum_words:
        value = value.rstrip(".") + ", " + suffix
        value = _ensure_sentence(value)
    return value


def _numbered(value: str, fallback: str, count: int, language: str, topic: str, kind: str) -> str:
    source = [_body(line) for line in _lines(value)]
    backup = [_body(line) for line in _lines(fallback)]
    for item in backup:
        if len(source) >= count:
            break
        if item not in source:
            source.append(item)

    if language == "ar":
        additions = {
            "outcomes": [
                f"يحلل المتطلبات القبلية المرتبطة بدرس {topic} ويحدد القاعدة الأنسب قبل بدء الحل",
                f"يطبق المفاهيم الأساسية في درس {topic} على مسائل متدرجة مع توضيح كل خطوة رياضية",
                "يفسر العلاقة بين التمثيل الجبري والتمثيل البياني أو العددي باستخدام مصطلحات رياضية دقيقة",
                "يقارن بين استراتيجيتين للحل ويبرر اختيار الاستراتيجية الأكثر كفاءة وفق معطيات المسألة",
                "يكتشف خطأً شائعًا في حل معروض ويصححه مع بيان السبب الرياضي للتصحيح",
                "يوظف التعلم في مسألة سياقية مرتبطة بالهوية الوطنية أو الاستدامة ويتحقق من معقولية الناتج",
            ],
            "criteria": [
                "أحدد القاعدة أو المفهوم المطلوب من معطيات السؤال دون مساعدة مباشرة",
                "أنفذ خطوات الحل بالترتيب الصحيح مستخدمًا رموزًا ومصطلحات رياضية دقيقة",
                "أشرح سبب كل خطوة وأربطها بالقاعدة المستخدمة بدل الاكتفاء بكتابة الناتج",
                "أتحقق من صحة الناتج بالتعويض أو التقدير أو المقارنة بتمثيل آخر مناسب",
                "أصحح خطأً مفاهيميًا أو إجرائيًا وأوضح أثره في الإجابة النهائية",
                "أحقق نسبة إتقان لا تقل عن 80% في مهمة التقويم الختامية المستقلة",
            ],
        }
        suffix = (
            "مع تبرير الاختيار وكتابة خطوات منظمة واستخدام لغة رياضية صحيحة"
            if kind == "outcomes"
            else "مع تقديم دليل واضح يمكن للمعلم ملاحظته وقياسه داخل الحصة"
        )
    else:
        additions = {
            "outcomes": [
                f"Analyse the prerequisite knowledge for {topic} and select an appropriate method before beginning the solution",
                f"Apply the central ideas of {topic} to progressively challenging questions while explaining each mathematical step",
                "Interpret relationships between algebraic, graphical, and numerical representations using accurate mathematical vocabulary",
                "Compare two possible strategies and justify the more efficient method using evidence from the question",
                "Identify and correct a common misconception, explaining how the error changes the final result",
                "Transfer learning to a contextual UAE or sustainability problem and evaluate whether the answer is reasonable",
            ],
            "criteria": [
                "I identify the required rule or concept from the question without direct teacher support",
                "I complete the solution in the correct sequence using accurate notation and mathematical vocabulary",
                "I justify each important step by naming the rule or relationship that supports it",
                "I verify the final answer through substitution, estimation, or comparison with another representation",
                "I diagnose and correct a conceptual or procedural error and explain its effect on the solution",
                "I achieve at least 80 percent accuracy in the independent exit assessment",
            ],
        }
        suffix = (
            "with a justified choice, clearly sequenced working, and accurate mathematical communication"
            if kind == "outcomes"
            else "and provide observable evidence that can be assessed during the lesson"
        )

    for item in additions[kind]:
        if len(source) >= count:
            break
        source.append(item)

    enriched: list[str] = []
    for item in source[:count]:
        if language == "ar":
            enriched.append(_extend_ar(item, suffix, 15 if kind == "outcomes" else 13))
        else:
            enriched.append(_extend_en(item, suffix, 16 if kind == "outcomes" else 14))
    return "\n".join(f"{index}. {item}" for index, item in enumerate(enriched, 1))


def _differentiation(value: str, language: str, topic: str) -> str:
    existing = " ".join(_lines(value))
    if language == "ar":
        rows = [
            f"دعم: بطاقة خطوات مصورة، مثال جزئي محلول، تلوين الرموز الأساسية، وأسئلة قصيرة متدرجة مرتبطة بدرس {topic}.",
            "المستوى المتوقع: تدريب موجه ثم مسألتان مستقلتان مع مقارنة الحل بنموذج نجاح واضح والتحقق من الناتج.",
            "متقدمون: مسألة متعددة الخطوات تتطلب اختيار الاستراتيجية وتبريرها، ثم تعميم النتيجة أو ربطها بتمثيل آخر.",
            "IEP/APL: تقليل الحمل الحسابي، تبسيط صياغة السؤال، توفير وقت إضافي، وشريك داعم مع الحفاظ على هدف التعلم.",
        ]
    else:
        rows = [
            f"Support: provide a visual step card, a partially completed model, highlighted notation, and graduated prompts for {topic}.",
            "Expected level: complete guided practice followed by two independent questions, using a clear success model to verify the result.",
            "Advanced: solve a multi-step problem that requires strategy selection, justification, and a generalisation or alternative representation.",
            "IEP/APL: reduce computational load, simplify wording, provide additional processing time, and use a supportive peer while preserving the objective.",
        ]
    if _word_count(existing) > 85:
        return "\n".join(_lines(value)[:4])
    return "\n".join(rows)


def _strategies(value: str, language: str, topic: str) -> str:
    existing = _lines(value)
    if language == "ar":
        defaults = [
            f"1. تمهيد استرجاعي قصير يكشف المتطلبات القبلية والتصورات الخاطئة قبل الانتقال إلى درس {topic}.",
            "2. نمذجة تفكير المعلم بصوت مرتفع مع توضيح سبب اختيار القاعدة وكتابة الخطوات في تسلسل بصري منظم.",
            "3. تدريب موجه باستخدام ألواح صغيرة وأسئلة تحقق فورية، ثم مناقشة خطأ شائع وتصحيحه بصورة جماعية.",
            "4. تعلم تعاوني ثنائي يتبعه تطبيق فردي متدرج وبطاقة خروج تقدم دليلًا واضحًا على مستوى الإتقان.",
        ]
    else:
        defaults = [
            f"1. Begin with a retrieval task that checks prerequisite knowledge and exposes misconceptions before teaching {topic}.",
            "2. Model expert thinking aloud, explaining why each rule is selected and presenting the working in a clear visual sequence.",
            "3. Use guided practice, mini-whiteboards, and immediate checks for understanding, followed by analysis of a common error.",
            "4. Move from paired reasoning to graduated independent practice and finish with an exit task that provides measurable evidence.",
        ]
    if len(existing) >= 4 and _word_count(" ".join(existing)) >= 65:
        return "\n".join(existing[:5])
    return "\n".join(defaults)


def _intervention(value: str, language: str, topic: str) -> str:
    existing = _lines(value)
    if language == "ar":
        defaults = [
            f"دعم فوري: إعادة تمثيل الفكرة في درس {topic} باستخدام مثال أبسط وبطاقة خطوات وأسئلة موجهة قصيرة.",
            "خطأ متوقع: تحديد الخطأ المفاهيمي أو الإجرائي من إجابات البداية، ثم استخدام مثال مضاد وتصحيح مشترك.",
            "إعادة التدريس: عند انخفاض الإتقان عن 75% تنفذ مجموعة مصغرة لمدة خمس دقائق مع نموذج جديد وتحقق فوري.",
            "إثراء ومتابعة: يقدم للمتقنين تحدٍ تبريري، بينما يسجل المعلم أسماء المحتاجين للدعم وخطوة المتابعة التالية.",
        ]
    else:
        defaults = [
            f"Immediate support: reteach the key idea in {topic} with a simpler example, a step card, and short guided prompts.",
            "Likely misconception: identify the conceptual or procedural error from starter evidence, then use a counterexample and shared correction.",
            "Reteaching trigger: when mastery falls below 75 percent, run a five-minute focus group with a new model and immediate checking.",
            "Extension and follow-up: provide a justification challenge for secure learners and record the next support action for identified students.",
        ]
    if len(existing) >= 4 and _word_count(" ".join(existing)) >= 65:
        return "\n".join(existing[:5])
    return "\n".join(defaults)


def _success_kpi(value: str, language: str, topic: str) -> str:
    if language == "ar":
        return (
            f"مهمة AFL: ثلاث مسائل متدرجة في {topic}: تطبيق مباشر، تصحيح خطأ، ومسألة تبرير قصيرة.\n"
            "دليل التعلم: خطوات مكتوبة، تفسير شفهي مختصر، والتحقق من الناتج بطريقة ثانية.\n"
            "معيار النجاح: إتقان 80% فأكثر مع عدم وجود خطأ مفاهيمي رئيس، وتقديم تغذية راجعة فورية للخطوة التالية."
        )
    return (
        f"AFL task: three graduated questions on {topic}: direct application, error correction, and a short justification problem.\n"
        "Learning evidence: written working, a concise oral explanation, and verification using a second method.\n"
        "Success threshold: at least 80 percent accuracy with no major conceptual error, followed by immediate next-step feedback."
    )


def _enrich(lesson, output: dict, fallback: dict) -> dict:
    language = lesson.language
    topic = lesson.topic.strip() or ("الدرس" if language == "ar" else "the lesson")
    result = dict(output)
    result["strategies"] = _strategies(str(result.get("strategies", "")), language, topic)
    result["intervention"] = _intervention(str(result.get("intervention", "")), language, topic)
    result["learning_outcomes"] = _numbered(
        str(result.get("learning_outcomes", "")), str(fallback.get("learning_outcomes", "")), 6, language, topic, "outcomes"
    )
    result["differentiation"] = _differentiation(str(result.get("differentiation", "")), language, topic)
    result["success_criteria"] = _numbered(
        str(result.get("success_criteria", "")), str(fallback.get("success_criteria", "")), 6, language, topic, "criteria"
    )
    if _word_count(str(result.get("kpi", ""))) < 35:
        result["kpi"] = _success_kpi(str(result.get("kpi", "")), language, topic)
    result["_density_qa"] = "balanced-content-v1"
    return result


def install(lesson_engine) -> None:
    original_build = lesson_engine.build_expert_content
    original_prompt = lesson_engine.system_prompt

    def detailed_prompt(language: str) -> str:
        base = original_prompt(language)
        if language == "ar":
            return base + (
                "\nاكتب خطة درس تنفيذية عالمية ومفصلة، لا ملخصًا عامًا. استخدم موضوع الدرس والنص المرجعي في كل قسم. "
                "الاستراتيجيات: أربع نقاط عملية، كل نقطة 18 إلى 28 كلمة. التدخل العلاجي: أربع نقاط معنونة تشمل الدعم الفوري، الخطأ المتوقع، شرط إعادة التدريس، والإثراء والمتابعة. "
                "نواتج التعلم: ستة نواتج متدرجة وفق بلوم، كل ناتج 16 إلى 24 كلمة ويحتوي فعلًا سلوكيًا ومحتوى الدرس ودليل أداء. "
                "التمايز: أربعة مستويات مفصلة، كل مستوى 18 إلى 30 كلمة. معايير النجاح: ستة معايير قابلة للملاحظة والقياس، كل معيار 14 إلى 22 كلمة. "
                "التمهيد والأنشطة ودور المعلم ودور الطلاب والخاتمة يجب أن تتضمن تعليمات فعلية، أسئلة محددة، استجابات متوقعة، أدلة تعلم، وتغذية راجعة. "
                "استخدم مثالًا رياضيًا صحيحًا وتدريبًا موجهًا وتطبيقًا فرديًا وسؤال تفكير عليا. لا تستخدم عبارات مثل يناقش المعلم الموضوع دون توضيح ماذا يفعل وكيف يقيس التعلم. "
                "ضع كل نقطة في سطر مستقل، ولا تضف أسطرًا فارغة، ولا تكرر الفكرة أو المصطلح بصيغ مختلفة."
            )
        return base + (
            "\nProduce an implementation-ready international lesson plan rather than a brief summary. Use the lesson topic and reference text throughout. "
            "Strategies: four practical points of 18 to 28 words each. Intervention: four labelled points covering immediate support, likely misconception, reteaching trigger, and extension/follow-up. "
            "Learning outcomes: exactly six progressive Bloom-aligned outcomes, each 16 to 24 words with an observable verb, lesson content, and performance evidence. "
            "Differentiation: four detailed levels of 18 to 30 words. Success criteria: exactly six observable and measurable criteria of 14 to 22 words. "
            "Starter, main activities, teacher role, student role, and plenary must contain precise instructions, named questions, expected responses, learning evidence, and feedback actions. "
            "Include one mathematically verified worked example, guided practice, independent application, and a higher-order challenge. Put every item on a separate line with no blank lines or repeated ideas."
        )

    def build(lesson, app):
        output = original_build(lesson, app)
        fallback = lesson_engine.special(lesson, app)
        return _enrich(lesson, output, fallback)

    lesson_engine.system_prompt = detailed_prompt
    lesson_engine.build_expert_content = build
