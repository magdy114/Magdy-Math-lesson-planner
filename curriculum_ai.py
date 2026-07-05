from __future__ import annotations

import math
import os
import re
from typing import Iterable

from curriculum_models import ComplianceItem, HalfTerm, LongPlan, MediumPlan, MediumWeek


def _clean_topic(topic: str) -> str:
    topic = re.sub(r"^\d+(?:\.\d+)*\s*[-.:)]?\s*", "", topic).strip()
    return topic or "Core subject concepts"


def _group_topics(topics: list[str], slots: int) -> list[list[str]]:
    cleaned = [_clean_topic(x) for x in topics if x.strip()]
    if not cleaned:
        cleaned = ["Introduction and prior knowledge", "Core concepts", "Applications", "Review and assessment"]
    groups: list[list[str]] = [[] for _ in range(slots)]
    if len(cleaned) <= slots:
        for i in range(slots):
            base = cleaned[min(i, len(cleaned) - 1)]
            if i >= len(cleaned):
                suffix = ["Practice and consolidation", "Applications and problem solving", "Review and assessment"][i % 3]
                groups[i] = [base, suffix]
            else:
                groups[i] = [base]
        return groups
    for i, topic in enumerate(cleaned):
        groups[min(slots - 1, math.floor(i * slots / len(cleaned)))].append(topic)
    return groups


def _join(items: Iterable[str], sep: str = "; ") -> str:
    return sep.join(x.strip() for x in items if x and x.strip())


def _medium_fallback(meta: dict, topics: list[str], language: str) -> MediumPlan:
    groups = _group_topics(topics, 14)
    ar = language == "Arabic"
    weeks: list[MediumWeek] = []
    for group in groups:
        content = _join(group, "؛ " if ar else "; ")
        focus = group[0]
        if ar:
            objectives = f"يشرح المفاهيم الأساسية في {focus}.\nيطبق الاستراتيجيات المناسبة لحل مسائل مرتبطة بالموضوع."
            ai = "يستخدم أداة ذكاء اصطناعي معتمدة لمقارنة طرق الحل والتحقق من المنطق دون مشاركة بيانات شخصية."
            resources = "الكتاب المدرسي، السبورة التفاعلية، أوراق عمل، GeoGebra/Desmos، مساعد ذكاء اصطناعي معتمد."
        else:
            objectives = f"Explain the key concepts in {focus}.\nApply suitable strategies to solve related problems and justify reasoning."
            ai = "Use an approved AI tool to compare strategies and verify reasoning without sharing personal data."
            resources = "Textbook, interactive board, worksheets, GeoGebra/Desmos, approved AI assistant."
        weeks.append(MediumWeek(content=content, learning_objectives=objectives, ai_literacy=ai, resources=resources))

    teacher = meta.get("teacher", "Teacher")
    if ar:
        return MediumPlan(
            title=f"الخطة متوسطة المدى - {meta['subject']} - {meta['grade']}",
            targets="إكمال محتوى الفصل وفق التسلسل المنطقي، رفع مستوى الإتقان، وتطوير التفكير الناقد والاستخدام المسؤول للذكاء الاصطناعي.",
            weeks=weeks,
            assessment_opportunities="تقويم قبلي، أسئلة صفية، مهام أداء، اختبارات قصيرة، مشروع تطبيقي، تقويم ختامي.",
            century_skills="التفكير الناقد، حل المشكلات، التواصل، التعاون، الإبداع، الثقافة الرقمية.",
            vocabulary=_join([_clean_topic(t) for t in topics[:12]], "، "),
            eps_guiding_statement="تعلم عالي الجودة من خلال الاستقصاء، التفكير الناقد، التعاون، والتطبيقات الواقعية مع المسؤولية والاحترام.",
            global_citizenship="التنمية المستدامة، التواصل، احترام التنوع، واتخاذ القرارات المسؤولة.",
            cross_curricular="روابط مع العلوم والتقنية والبيانات والاستدامة وفق طبيعة موضوعات المادة.",
            national_identity="المجال: الثقافة، القيم، المواطنة. الأبعاد: الاحترام، التراث، الانتماء، المحافظة على الموارد.",
            ai_integration_approach="استخدام موجه للذكاء الاصطناعي في توليد أمثلة، مقارنة الاستراتيجيات، التغذية الراجعة والتحقق من الفهم.",
            guardrails_prompt_controls="استخدام أدوات معتمدة فقط، منع إدخال البيانات الشخصية، تحديد المهمة والسياق، ومراجعة المعلم للمخرجات.",
            cognitive_integrity_strategy="يقدم الطالب محاولة أولية وشرحًا شفهيًا أو كتابيًا قبل استخدام الذكاء الاصطناعي، ثم يقارن ويصحح ولا ينسخ الإجابة.",
            ai_safeguarding="تطبيق الخصوصية الرقمية، التحقق من الدقة والتحيز، الاستشهاد بالمساعدة الرقمية، وعدم رفع بيانات أو صور شخصية.",
            compliance=[
                ComplianceItem(area="تكامل المنهج", milestone="تضمين نشاط ذكاء اصطناعي آمن في كل وحدة", responsible_person=teacher, target_date="خلال الفصل", status="قيد التنفيذ"),
                ComplianceItem(area="تعرض الطلبة", milestone="تدريب الطلبة على جودة الأوامر والتحقق والاستخدام المسؤول", responsible_person=teacher, target_date="قبل الأسبوع 4", status="مخطط"),
                ComplianceItem(area="النزاهة المعرفية", milestone="إلزام المحاولة الأولى وشرح التفكير قبل دعم الذكاء الاصطناعي", responsible_person=teacher, target_date="كل مهمة AI", status="قيد التنفيذ"),
                ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة وعدم مشاركة بيانات شخصية", responsible_person=teacher, target_date="خلال الفصل", status="قيد التنفيذ"),
            ],
        )
    return MediumPlan(
        title=f"Medium Term Plan - {meta['subject']} - {meta['grade']}",
        targets="Complete the term curriculum in a coherent sequence, improve mastery, and develop critical thinking and responsible AI use.",
        weeks=weeks,
        assessment_opportunities="Diagnostic checks, questioning, performance tasks, quizzes, an applied project, and summative assessment.",
        century_skills="Critical thinking, problem solving, communication, collaboration, creativity, and digital literacy.",
        vocabulary=_join([_clean_topic(t) for t in topics[:12]], ", "),
        eps_guiding_statement="High-quality learning through inquiry, critical thinking, collaboration, real-world application, responsibility, and respect.",
        global_citizenship="Sustainable development, communication, valuing diversity, and responsible decision-making.",
        cross_curricular="Links to science, technology, data analysis, and sustainability according to the subject content.",
        national_identity="Domain: Culture, Values, Citizenship. Dimensions: respect, heritage, belonging, and conservation.",
        ai_integration_approach="Teacher-guided AI use for examples, strategy comparison, feedback, and checking understanding.",
        guardrails_prompt_controls="Use approved tools only; never enter personal data; constrain prompts to the lesson; teacher reviews all outputs.",
        cognitive_integrity_strategy="Students submit an initial attempt and explain reasoning before AI use, then compare and improve rather than copy.",
        ai_safeguarding="Apply data privacy, accuracy and bias checks, acknowledge AI assistance, and never upload personal information or images.",
        compliance=[
            ComplianceItem(area="Curriculum Integration", milestone="Include one safe AI-supported activity in each unit", responsible_person=teacher, target_date="Throughout term", status="In progress"),
            ComplianceItem(area="Student Exposure", milestone="Teach prompt quality, verification, and responsible use", responsible_person=teacher, target_date="By Week 4", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Require first attempts and reasoning before AI support", responsible_person=teacher, target_date="Every AI task", status="In progress"),
            ComplianceItem(area="Privacy & Safety", milestone="Use approved tools and share no personal data", responsible_person=teacher, target_date="Throughout term", status="In progress"),
        ],
    )


def _long_fallback(meta: dict, topics: list[str], language: str) -> LongPlan:
    groups = _group_topics(topics, 6)
    titles = ["Autumn 1 (HT1)", "Autumn 2 (HT2)", "Spring 1 (HT3)", "Spring 2 (HT4)", "Summer 1 (HT5)", "Summer 2 (HT6)"]
    ar = language == "Arabic"
    half_terms: list[HalfTerm] = []
    for i, group in enumerate(groups):
        if ar:
            content = "\n".join(f"• {x}" for x in group)
            assessment = "اختبار قصير، مهمة أداء، ومراجعة تراكمية."
        else:
            content = "\n".join(f"• {x}" for x in group)
            assessment = "Quiz, performance task, and cumulative review."
        half_terms.append(HalfTerm(title=titles[i], content=content, summative_assessment=assessment))
    teacher = meta.get("teacher", "Teacher")
    if ar:
        compliance = [
            ComplianceItem(area="تكامل المنهج", milestone="ربط الذكاء الاصطناعي بأهداف تعلم محددة", responsible_person=teacher, target_date="نهاية HT2", status="مخطط"),
            ComplianceItem(area="تعرض الطلبة", milestone="تدريب الطلبة على الاستخدام الآمن والتحقق من المخرجات", responsible_person=teacher, target_date="نهاية HT3", status="مخطط"),
            ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة الأولى وشرح التفكير قبل دعم الذكاء الاصطناعي", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ"),
            ComplianceItem(area="الخصوصية والسلامة", milestone="عدم مشاركة أي بيانات شخصية واستخدام أدوات معتمدة", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ"),
        ]
    else:
        compliance = [
            ComplianceItem(area="Curriculum Integration", milestone="Connect AI use to specific learning objectives", responsible_person=teacher, target_date="End of HT2", status="Planned"),
            ComplianceItem(area="Student Exposure", milestone="Train students in safe use and output verification", responsible_person=teacher, target_date="End of HT3", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Record first attempts and reasoning before AI support", responsible_person=teacher, target_date="Throughout year", status="In progress"),
            ComplianceItem(area="Privacy & Safety", milestone="Use approved tools and share no personal data", responsible_person=teacher, target_date="Throughout year", status="In progress"),
        ]
    return LongPlan(half_terms=half_terms, compliance=compliance)


def _source_prompt(meta: dict, source_text: str, topics: list[str], language: str, instructions: str) -> str:
    topic_block = "\n".join(f"- {x}" for x in topics[:100])
    return f"""
Teacher: {meta.get('teacher')}
Subject: {meta.get('subject')}
Grade group: {meta.get('grade')}
Academic year: {meta.get('academic_year')}
Output language: {language}
Additional instructions: {instructions or 'None'}

Candidate curriculum topics:
{topic_block or 'No clean topic list was detected; infer from source text.'}

Extracted source text:
{source_text[:55_000]}
""".strip()


def generate_medium(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> MediumPlan:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _medium_fallback(meta, topics, language)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        system = """You are an expert UAE school curriculum planner. Create a Medium Term Plan that exactly fits the supplied EPS template. Produce exactly 14 instructional weeks; do not create an entry for the mid-term break. Keep every cell concise enough for a landscape Word table. Use measurable Bloom-aligned objectives, safe purposeful AI literacy, approved educational resources, UAE national identity, sustainability, cross-curricular links, assessment opportunities, cognitive integrity, privacy, and compliance. Do not invent curriculum topics beyond reasonable review/application activities. Output only the structured plan."""
        response = client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            input=[{"role": "system", "content": system}, {"role": "user", "content": _source_prompt(meta, source_text, topics, language, instructions)}],
            text_format=MediumPlan,
        )
        plan = response.output_parsed
        if not plan or len(plan.weeks) != 14:
            raise ValueError("AI returned an invalid number of weeks")
        if not plan.compliance:
            plan.compliance = _medium_fallback(meta, topics, language).compliance
        return plan
    except Exception:
        return _medium_fallback(meta, topics, language)


def generate_long(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> LongPlan:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _long_fallback(meta, topics, language)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        system = """You are an expert UAE school curriculum planner. Create a full-year Long Term Plan for the supplied EPS template. Produce exactly six half-terms in this order: Autumn 1, Autumn 2, Spring 1, Spring 2, Summer 1, Summer 2. Distribute the supplied curriculum logically, keep each cell concise and bullet-ready, include summative assessment opportunities, and provide exactly four AI implementation/compliance rows covering curriculum integration, student exposure, cognitive integrity, and privacy/safety. Output only the structured plan."""
        response = client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            input=[{"role": "system", "content": system}, {"role": "user", "content": _source_prompt(meta, source_text, topics, language, instructions)}],
            text_format=LongPlan,
        )
        plan = response.output_parsed
        if not plan or len(plan.half_terms) != 6:
            raise ValueError("AI returned an invalid number of half-terms")
        if len(plan.compliance) < 4:
            plan.compliance = _long_fallback(meta, topics, language).compliance
        return plan
    except Exception:
        return _long_fallback(meta, topics, language)
