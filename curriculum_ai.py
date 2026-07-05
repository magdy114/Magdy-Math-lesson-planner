from __future__ import annotations

import logging
import math
import os
import re
from typing import Iterable

from curriculum_models import ComplianceItem, HalfTerm, LongPlan, MediumPlan, MediumWeek, TopicExtraction

logger = logging.getLogger("magdy_lesson_planner.curriculum")

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
PLAN_NOISE = (
    "copyright", "all rights reserved", "rights reserved", "mcgraw", "pearson", "publisher",
    "publishing", "isbn", "sourced from", "education, llc", "trademark", "www.", "http://",
    "https://", "©", "®", "™", "differentiation", "example", "exercise", "solution",
    "حقوق الطبع", "جميع الحقوق محفوظة", "الناشر", "الطبعة", "حقوق النشر", "المصدر",
    "مثال", "تمرين", "الحل", "الشكل", "تحذير", "لاحظ", "تذكر",
)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ai_client(api_key: str, timeout_seconds: float):
    from openai import OpenAI
    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def _strip_numbering(text: str) -> str:
    text = str(text or "").translate(ARABIC_DIGITS)
    text = re.sub(r"^\s*\[HEADING\]\s*", "", text, flags=re.I)
    labels = r"unit|chapter|lesson|section|module|topic|الوحدة|الفصل|الدرس|القسم|الباب|الموضوع"
    text = re.sub(
        rf"^\s*(?:{labels})\s*(?:no\.?|رقم)?\s*[0-9]+(?:[.\-][0-9]+)*\s*[:\-–—|]*\s*",
        "", text, flags=re.I,
    )
    text = re.sub(r"^\s*[0-9]+(?:[.\-][0-9]+){1,3}\s*[:\-–—|]*\s*", "", text)
    text = re.sub(
        rf"\s*[|\-–—:]\s*(?:{labels})?\s*[0-9]+(?:[.\-][0-9]+)*\s*$",
        "", text, flags=re.I,
    )
    text = re.sub(r"\.{2,}\s*[0-9]+\s*$", "", text)
    text = re.sub(r"(?<![A-Za-z])\b[0-9]+(?:[.\-][0-9]+)*\b(?![A-Za-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip(" •-–—|:;,.")


def _is_noise(text: str) -> bool:
    lower = str(text or "").casefold()
    return any(term in lower for term in PLAN_NOISE)


def _clean_topic(topic: str) -> str:
    topic = _strip_numbering(topic)
    topic = re.sub(r"\s+", " ", topic).strip(" •-–—|:;,.")
    if not topic or _is_noise(topic):
        return ""
    words = topic.split()
    if not (1 <= len(words) <= 13) or len(topic) > 105:
        return ""
    if sum(ch.isdigit() for ch in topic) > 1:
        return ""
    if sum(ch in "+=<>[]{}()" for ch in topic) >= 3:
        return ""
    if re.search(r"[.!?؟؛]$", topic):
        return ""
    return topic


def clean_topics(topics: list[str], limit: int = 90) -> list[str]:
    output: list[str] = []
    seen: list[str] = []
    for raw in topics:
        topic = _clean_topic(raw)
        if not topic:
            continue
        key = re.sub(r"[^\w\u0600-\u06ff]+", "", topic.casefold())
        if not key or any(key == old or (min(len(key), len(old)) >= 10 and (key in old or old in key)) for old in seen):
            continue
        seen.append(key)
        output.append(topic)
        if len(output) >= limit:
            break
    return output


def refine_topics(meta: dict, source_text: str, candidates: list[str], language: str) -> list[str]:
    """Run one compact validation pass, never sending book prose to the model."""
    base = clean_topics(candidates)
    if not base:
        return []
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not _env_flag("CURRICULUM_AI_REFINEMENT", True):
        return base
    try:
        client = _ai_client(api_key, float(os.getenv("CURRICULUM_REFINE_TIMEOUT", "10")))
        system = (
            "You are a strict curriculum-title editor. Return only genuine ordered unit, chapter, "
            "section, and lesson titles. Delete publisher/legal text, page or lesson numbers, examples, "
            "questions, equations, narrative sentences, warnings, figures, and fragments. Never invent "
            "new curriculum content. Preserve the original Arabic or English wording and return concise "
            "teachable titles only, with no numbering and no commentary."
        )
        prompt = (
            f"Subject: {meta.get('subject')}\nGrade: {meta.get('grade')}\n"
            f"Output language: {language}\n\nCandidate titles:\n"
            + "\n".join(f"- {item}" for item in base[:70])
        )
        response = client.responses.parse(
            model=os.getenv("CURRICULUM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
            input=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            text_format=TopicExtraction,
        )
        parsed = response.output_parsed
        refined = clean_topics(parsed.topics if parsed else [])
        if len(refined) >= 2:
            return refined
    except Exception as exc:
        logger.warning("Topic validation failed; using locally cleaned titles: %s", exc)
    return base


def _join(items: Iterable[str], sep: str = "; ") -> str:
    return sep.join(str(x).strip() for x in items if x and str(x).strip())


def _is_math(subject: str) -> bool:
    lower = (subject or "").casefold()
    return "math" in lower or "رياض" in lower or "calculus" in lower or "حساب" in lower


def _core_topic(text: str, language: str) -> str:
    text = _clean_topic(text) or ("موضوع المادة" if language == "Arabic" else "the topic")
    prefixes_ar = ("المفاهيم الأساسية في ", "تطبيقات ", "حل مشكلات في ", "مراجعة وتقويم ", "التعمق في ")
    prefixes_en = ("Foundations of ", "Applications of ", "Problem solving in ", "Review and assessment of ", "Advanced study of ")
    for prefix in (prefixes_ar if language == "Arabic" else prefixes_en):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _objective_pair(topic: str, subject: str, language: str) -> str:
    ar = language == "Arabic"
    focus = _core_topic(topic, language)
    low = focus.casefold()
    math = _is_math(subject)

    if ar and math:
        if "مماس" in low or "ميل" in low:
            return "يحسب ميل المماس عند نقطة باستخدام تمثيل مناسب.\nيكتب معادلة المماس ويفسر معناها بيانياً."
        if "سرعة" in low or "حركة" in low:
            return "يحسب السرعة المتوسطة واللحظية من بيانات أو دالة موقع.\nيفسر إشارة السرعة ووحداتها في سياق المسألة."
        if "نهاية" in low or "اتصال" in low:
            return "يحدد قيمة النهاية جبرياً وبيانياً باستخدام استراتيجية مناسبة.\nيبرر وجود النهاية أو عدم وجودها ويربطها باتصال الدالة."
        if "تكامل" in low:
            return "يحسب التكامل باستخدام الطريقة المناسبة.\nيفسر قيمة التكامل ويوظفها في مسألة تطبيقية."
        if "اشتقاق" in low or "مشتق" in low or "تفاضل" in low:
            return "يحسب مشتقات الدوال بدقة باستخدام القاعدة المناسبة.\nيوظف المشتقة في تحليل التغير وحل مسألة تطبيقية."
        if "سلسلة" in low:
            return "يحدد الدالة الداخلية والخارجية في تركيب دالتين.\nيطبق قاعدة السلسلة ويبرر خطوات الاشتقاق."
        if "قصوى" in low or "حرجة" in low:
            return "يحدد النقاط الحرجة ومجالات التزايد والتناقص.\nيستنتج القيم القصوى ويبررها باستخدام المشتقة."
        if "مساحة" in low:
            return "يمثل حدود المنطقة بين المنحنيات تمثيلاً صحيحاً.\nيحسب المساحة ويختبر معقولية الناتج."
        if "حجم" in low:
            return "يختار نموذج الحجم المناسب ويحدد حدود التكامل.\nيحسب الحجم ويبرر اختيار طريقة الحل."
        if "لوغاريتم" in low or "أسي" in low:
            return "يطبق خصائص الدوال الأسية واللوغاريتمية بدقة.\nيحل معادلات مرتبطة ويتحقق من صحة الحل."
        if "مثلث" in low or "جيب" in low or "جيب التمام" in low:
            return "يوظف العلاقات المثلثية في تبسيط تعبير أو حل معادلة.\nيمثل الحل ويفسر القيود على المجال."
        if "متجه" in low:
            return "يجري العمليات على المتجهات ويمثلها هندسياً.\nيوظف المتجهات في حل مسألة من سياق واقعي."
        if "مصفوف" in low:
            return "يجري العمليات على المصفوفات بدقة.\nيوظف المصفوفات في حل نظام أو تمثيل موقف تطبيقي."
        return f"يشرح المفاهيم والعلاقات الرياضية في {focus} باستخدام تمثيلات صحيحة.\nيحل مسائل متدرجة في {focus} ويبرر خطوات الحل."

    if not ar and math:
        if "tangent" in low or "slope" in low:
            return "Calculate the slope of a tangent using an appropriate representation.\nWrite and interpret the equation of the tangent line."
        if "velocity" in low or "motion" in low:
            return "Calculate average and instantaneous velocity from position data.\nInterpret sign, units, and meaning in context."
        if "limit" in low or "continu" in low:
            return "Evaluate limits algebraically and graphically.\nJustify whether a limit exists and connect it to continuity."
        if "integral" in low:
            return "Evaluate an integral using an appropriate method.\nInterpret and apply the result in context."
        if "derivative" in low or "differentiat" in low:
            return "Differentiate functions accurately using the appropriate rule.\nApply the derivative to analyze change and solve a contextual problem."
        return f"Explain the mathematical concepts and relationships in {focus}.\nSolve graded problems in {focus} and justify each method."

    if ar:
        return f"يحدد المفاهيم الرئيسة في {focus} ويشرح العلاقات بينها.\nيطبق المعرفة في مهمة متدرجة ويبرر استنتاجاته بالأدلة."
    return f"Identify and explain the key concepts in {focus}.\nApply learning in a graded task and justify conclusions with evidence."


def _ai_literacy(index: int, subject: str, language: str) -> str:
    ar = language == "Arabic"
    math = _is_math(subject)
    if ar and math:
        options = [
            "يقارن حله اليدوي بتمثيل رقمي، ويحدد سبب أي اختلاف قبل اعتماد النتيجة.",
            "يستخدم أداة معتمدة للتحقق من الرسم أو الحساب، ثم يشرح حدود دقتها.",
            "يقيّم خطوات حل مقترحة رقمياً، ويصحح الخطأ مع تقديم مبرر رياضي.",
            "يصوغ أمراً رقمياً واضحاً دون بيانات شخصية، ثم يتحقق من الناتج بطريقة مستقلة.",
        ]
    elif ar:
        options = [
            "يقارن استنتاجه الأولي بمصدر رقمي معتمد، ويتحقق من الدقة قبل الاعتماد.",
            "يقيّم مخرجاً رقمياً باستخدام معايير واضحة، ثم يبرر قراره بالأدلة.",
            "يصوغ أمراً واضحاً وآمناً، ويذكر كيف تحقق من موثوقية الناتج.",
        ]
    else:
        options = [
            "Compare an independent solution with an approved digital representation and explain any difference.",
            "Use an approved tool for verification, then state its limitations and check accuracy independently.",
            "Evaluate a suggested solution, correct errors, and justify the final decision with evidence.",
        ]
    return options[index % len(options)]


def _resources(subject: str, language: str) -> str:
    ar = language == "Arabic"
    if _is_math(subject):
        return (
            "الكتاب المدرسي، أوراق عمل متدرجة، GeoGebra/Desmos، آلة حاسبة بيانية، وبنك أسئلة معتمد."
            if ar else
            "Textbook, graded worksheets, GeoGebra/Desmos, graphing calculator, and an approved question bank."
        )
    return (
        "الكتاب المدرسي، مصادر بصرية موثوقة، أوراق عمل متدرجة، ومنصة رقمية معتمدة."
        if ar else
        "Textbook, reliable visual resources, graded worksheets, and an approved digital platform."
    )


def _phase_title(topic: str, phase: int, language: str) -> str:
    core = _core_topic(topic, language)
    if language == "Arabic":
        labels = [
            "المفاهيم الأساسية في", "التعمق في", "تطبيقات", "حل مشكلات في", "مراجعة وتقويم",
        ]
    else:
        labels = ["Foundations of", "Advanced study of", "Applications of", "Problem solving in", "Review and assessment of"]
    return f"{labels[phase % len(labels)]} {core}"


def _weekly_groups(topics: list[str], slots: int, language: str) -> list[list[str]]:
    clean = clean_topics(topics)
    if not clean:
        return [[] for _ in range(slots)]
    if len(clean) >= slots:
        groups: list[list[str]] = [[] for _ in range(slots)]
        for i, topic in enumerate(clean):
            groups[min(slots - 1, math.floor(i * slots / len(clean)))].append(topic)
        return groups

    groups = []
    for i in range(slots):
        topic_index = min(len(clean) - 1, math.floor(i * len(clean) / slots))
        repeated_before = sum(1 for j in range(i) if min(len(clean) - 1, math.floor(j * len(clean) / slots)) == topic_index)
        groups.append([_phase_title(clean[topic_index], repeated_before, language)])
    return groups


def _medium_plan(meta: dict, topics: list[str], language: str) -> MediumPlan:
    subject = meta.get("subject", "Subject")
    grade = meta.get("grade", "")
    teacher = meta.get("teacher", "Teacher")
    ar = language == "Arabic"
    groups = _weekly_groups(topics, 14, language)
    weeks: list[MediumWeek] = []
    for idx, group in enumerate(groups):
        content = _join(group[:3], "؛ " if ar else "; ")
        focus = group[0] if group else (subject if subject else "موضوع المادة")
        weeks.append(MediumWeek(
            content=content,
            learning_objectives=_objective_pair(focus, subject, language),
            ai_literacy=_ai_literacy(idx, subject, language),
            resources=_resources(subject, language),
        ))

    if ar:
        return MediumPlan(
            title=f"الخطة متوسطة المدى - {subject} - {grade}",
            targets="تغطية موضوعات الفصل بتسلسل معرفي واضح، رفع مستوى الإتقان، وتنمية الاستدلال وحل المشكلات والتعلم الرقمي المسؤول.",
            weeks=weeks,
            assessment_opportunities="تقويم تشخيصي، أسئلة صفية موجهة، مهام أداء، أوراق عمل متدرجة، اختبارات قصيرة، مراجعة تراكمية، وتقويم ختامي.",
            century_skills="التفكير الناقد، حل المشكلات، التواصل الرياضي، التعاون، الإبداع، الثقافة الرقمية، وإدارة التعلم.",
            vocabulary=_join(clean_topics(topics)[:10], "، "),
            eps_guiding_statement="تعلم عالي الجودة قائم على الاستقصاء، التفكير الناقد، التعاون، التغذية الراجعة، والتطبيقات الواقعية مع المسؤولية والاحترام.",
            global_citizenship="التنمية المستدامة، التواصل الفعال، احترام التنوع، واتخاذ قرارات مسؤولة قائمة على الأدلة.",
            cross_curricular="روابط هادفة مع العلوم والتقنية وتحليل البيانات والاستدامة بحسب طبيعة موضوعات المادة.",
            national_identity="المجال: الثقافة والقيم والمواطنة. الأبعاد المقترحة: الاحترام، الانتماء، التراث، والمحافظة على الموارد.",
            ai_integration_approach="استخدام تعليمي موجه للأدوات المعتمدة في التمثيل والتحقق والتغذية الراجعة، دون أن تحل محل تفكير الطالب.",
            guardrails_prompt_controls="تحديد المهمة والسياق، استخدام أدوات معتمدة، منع إدخال البيانات الشخصية، والتحقق من المخرجات قبل اعتمادها.",
            cognitive_integrity_strategy="يقدم الطالب محاولة أولية ويفسر تفكيره قبل الدعم الرقمي، ثم يقارن ويصحح ويوثق ما تعلمه.",
            ai_safeguarding="حماية الخصوصية، التحقق من الدقة والتحيز، عدم رفع بيانات أو صور شخصية، والإفصاح عن المساعدة الرقمية عند الحاجة.",
            compliance=[
                ComplianceItem(area="تكامل المنهج", milestone="اختيار استخدام رقمي مرتبط بهدف تعلم واضح", responsible_person=teacher, target_date="خلال الفصل", status="قيد التنفيذ"),
                ComplianceItem(area="تدريب الطلبة", milestone="تدريب الطلبة على التحقق والاستخدام المسؤول", responsible_person=teacher, target_date="قبل الأسبوع الرابع", status="مخطط"),
                ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة الأولى قبل الدعم الرقمي", responsible_person=teacher, target_date="في كل مهمة", status="قيد التنفيذ"),
                ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة دون بيانات شخصية", responsible_person=teacher, target_date="طوال الفصل", status="قيد التنفيذ"),
            ],
        )

    return MediumPlan(
        title=f"Medium Term Plan - {subject} - {grade}",
        targets="Sequence term content clearly, improve mastery, and develop reasoning, problem solving, and responsible digital learning.",
        weeks=weeks,
        assessment_opportunities="Diagnostic checks, targeted questioning, performance tasks, graded worksheets, quizzes, cumulative review, and summative assessment.",
        century_skills="Critical thinking, problem solving, subject communication, collaboration, creativity, digital literacy, and self-management.",
        vocabulary=_join(clean_topics(topics)[:10], ", "),
        eps_guiding_statement="High-quality learning through inquiry, critical thinking, collaboration, feedback, real-world application, responsibility, and respect.",
        global_citizenship="Sustainable development, effective communication, valuing diversity, and evidence-based responsible decisions.",
        cross_curricular="Purposeful links to science, technology, data analysis, and sustainability according to the subject content.",
        national_identity="Domain: Culture, Values, Citizenship. Suggested dimensions: respect, belonging, heritage, and conservation.",
        ai_integration_approach="Teacher-guided use of approved tools for representation, verification, and feedback without replacing student thinking.",
        guardrails_prompt_controls="Define task and context, use approved tools, enter no personal data, and verify outputs before acceptance.",
        cognitive_integrity_strategy="Students complete and explain a first attempt before digital support, then compare, correct, and document learning.",
        ai_safeguarding="Protect privacy, check accuracy and bias, upload no personal data or images, and acknowledge digital assistance where appropriate.",
        compliance=[
            ComplianceItem(area="Curriculum Integration", milestone="Select purposeful digital use linked to a learning objective", responsible_person=teacher, target_date="Throughout term", status="In progress"),
            ComplianceItem(area="Student Training", milestone="Train students in verification and responsible use", responsible_person=teacher, target_date="By Week Four", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Record an independent first attempt before digital support", responsible_person=teacher, target_date="Every task", status="In progress"),
            ComplianceItem(area="Privacy & Safety", milestone="Use approved tools without personal data", responsible_person=teacher, target_date="Throughout term", status="In progress"),
        ],
    )


def _long_groups(topics: list[str], language: str) -> list[list[str]]:
    clean = clean_topics(topics)
    if not clean:
        return [[] for _ in range(6)]
    if len(clean) >= 6:
        groups: list[list[str]] = [[] for _ in range(6)]
        for index, topic in enumerate(clean):
            groups[min(5, math.floor(index * 6 / len(clean)))].append(topic)
        return groups
    # With a short source, show a legitimate progression instead of book fragments.
    groups = []
    for i in range(6):
        topic_index = min(len(clean) - 1, math.floor(i * len(clean) / 6))
        repeats = sum(1 for j in range(i) if min(len(clean) - 1, math.floor(j * len(clean) / 6)) == topic_index)
        groups.append([_phase_title(clean[topic_index], repeats, language)])
    return groups


def _long_plan(meta: dict, topics: list[str], language: str) -> LongPlan:
    ar = language == "Arabic"
    groups = _long_groups(topics, language)
    titles = ["Autumn 1 (HT1)", "Autumn 2 (HT2)", "Spring 1 (HT3)", "Spring 2 (HT4)", "Summer 1 (HT5)", "Summer 2 (HT6)"]
    assessments_ar = [
        "اختبار تشخيصي ومهمة أداء قصيرة مع تغذية راجعة.",
        "اختبار تحصيلي ومهمة تطبيقية ومراجعة تراكمية.",
        "اختبار قصير وتحليل أخطاء ومهمة حل مشكلات.",
        "تقويم تحصيلي ومشروع أو مهمة أداء مرتبطة بالمحتوى.",
        "مهمة تطبيقية، اختبار قصير، ومراجعة مترابطة.",
        "تقويم ختامي، مراجعة شاملة، وتحليل مستوى الإتقان.",
    ]
    assessments_en = [
        "Diagnostic assessment and a short performance task with feedback.",
        "Achievement test, applied task, and cumulative review.",
        "Quiz, error analysis, and a problem-solving task.",
        "Achievement assessment and a content-linked project or performance task.",
        "Applied task, quiz, and connected review.",
        "Summative assessment, comprehensive review, and mastery analysis.",
    ]
    halves: list[HalfTerm] = []
    for idx, group in enumerate(groups):
        content = "\n".join(f"• {item}" for item in group[:7])
        halves.append(HalfTerm(
            title=titles[idx],
            content=content,
            summative_assessment=(assessments_ar if ar else assessments_en)[idx],
        ))
    teacher = meta.get("teacher", "Teacher")
    compliance = [
        ComplianceItem(area="Curriculum Integration", milestone="Purposeful digital use linked to curriculum goals", responsible_person=teacher, target_date="End of HT2", status="Planned"),
        ComplianceItem(area="Student Exposure", milestone="Safe-use and verification routines established", responsible_person=teacher, target_date="End of HT3", status="Planned"),
        ComplianceItem(area="Cognitive Integrity", milestone="Independent first attempts documented", responsible_person=teacher, target_date="Throughout year", status="In progress"),
        ComplianceItem(area="Privacy & Safety", milestone="Approved tools used without personal data", responsible_person=teacher, target_date="Throughout year", status="In progress"),
    ]
    return LongPlan(half_terms=halves, compliance=compliance)


def generate_medium(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> MediumPlan:
    # The professional deterministic planner is intentionally used in the request path.
    # It is fast on Render and prevents fabricated book content or timeout errors.
    return _medium_plan(meta, clean_topics(topics), language)


def generate_long(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> LongPlan:
    return _long_plan(meta, clean_topics(topics), language)
