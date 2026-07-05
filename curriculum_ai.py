from __future__ import annotations

import logging
import math
import os
import re
from typing import Iterable

from curriculum_models import ComplianceItem, HalfTerm, LongPlan, MediumPlan, MediumWeek, TopicExtraction

logger = logging.getLogger("magdy_lesson_planner.curriculum")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ai_client(api_key: str, timeout_seconds: float):
    """Create a fail-fast OpenAI client so a slow model call never kills the Render request."""
    from openai import OpenAI
    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

PLAN_NOISE = (
    "copyright", "all rights reserved", "rights reserved", "mcgraw", "pearson", "publisher",
    "publishing", "isbn", "sourced from", "education, llc", "trademark", "www.", "http://",
    "https://", "©", "®", "™", "for differentiation", "differentiation",
    "حقوق الطبع", "جميع الحقوق محفوظة", "الناشر", "الطبعة", "حقوق النشر", "المصدر",
)


def _is_noise(text: str) -> bool:
    lower = (text or "").casefold()
    return any(term in lower for term in PLAN_NOISE)


def _clean_topic(topic: str) -> str:
    topic = re.sub(r"^\[HEADING\]\s*", "", str(topic or ""), flags=re.I)
    topic = re.sub(r"^[•\-–—]+\s*", "", topic)
    topic = re.sub(r"\.{2,}\s*\d+\s*$", "", topic)
    topic = re.sub(r"\s+", " ", topic).strip(" -–—|:;,.\t")
    if not topic or _is_noise(topic):
        return ""
    if len(topic) > 130:
        return ""
    if len(topic.split()) > 16:
        return ""
    if sum(ch.isdigit() for ch in topic) >= 6:
        return ""
    return topic


def clean_topics(topics: list[str], limit: int = 100) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in topics:
        topic = _clean_topic(raw)
        if not topic:
            continue
        key = re.sub(r"[^\w\u0600-\u06ff]+", "", topic.casefold())
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(topic)
        if len(output) >= limit:
            break
    return output


def refine_topics(meta: dict, source_text: str, candidates: list[str], language: str) -> list[str]:
    """Return clean ordered headings without a second slow AI request in normal use.

    Local extraction is authoritative. AI refinement is used only when very few headings were
    detected and can be explicitly disabled/enabled with CURRICULUM_AI_REFINEMENT.
    """
    base = clean_topics(candidates)
    # A useful local heading list is both faster and safer than sending a whole book twice.
    if len(base) >= 6 or not _env_flag("CURRICULUM_AI_REFINEMENT", False):
        return base

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return base
    try:
        client = _ai_client(api_key, float(os.getenv("CURRICULUM_REFINE_TIMEOUT", "20")))
        system = """You are a curriculum index extraction specialist. Extract ONLY ordered curriculum unit, chapter, section, and lesson titles. Ignore and never return copyright notices, publisher names, ISBNs, author information, page numbers, website addresses, learning examples, exercise questions, explanatory paragraphs, worked solutions, differentiation notes, or legal text. Preserve the source language. A topic must be a concise teachable heading, not a sentence from the book. Prefer the supplied candidate headings and preserve their sequence. Return no commentary."""
        candidate_block = "\n".join(f"- {x}" for x in base[:60]) or "No reliable headings were detected."
        prompt = f"""
Subject: {meta.get('subject')}
Grade: {meta.get('grade')}
Required output language: {language}

Candidate headings (highest priority):
{candidate_block}

Short reference extract (headings only; never copy prose):
{source_text[:8_000]}
""".strip()
        response = client.responses.parse(
            model=os.getenv("CURRICULUM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini")),
            input=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            text_format=TopicExtraction,
        )
        parsed = response.output_parsed
        refined = clean_topics(parsed.topics if parsed else [])
        if len(refined) >= 3:
            return clean_topics(refined + base)
    except Exception as exc:
        logger.warning("Curriculum topic refinement timed out or failed; using local headings: %s", exc)
    return base


def _group_topics(topics: list[str], slots: int, subject: str = "Subject", language: str = "English") -> list[list[str]]:
    cleaned = clean_topics(topics)
    if not cleaned:
        cleaned = [
            f"{subject}: prior knowledge and foundations",
            f"{subject}: core concepts",
            f"{subject}: applications and problem solving",
            f"{subject}: review and assessment",
        ]
    groups: list[list[str]] = [[] for _ in range(slots)]
    if len(cleaned) <= slots:
        for i in range(slots):
            if i < len(cleaned):
                groups[i] = [cleaned[i]]
            else:
                base = cleaned[min(len(cleaned) - 1, max(0, i % len(cleaned)))]
                suffixes = (["تدريب موجه", "تطبيقات", "مراجعة وتثبيت"] if language == "Arabic"
                            else ["Guided practice", "Applications", "Consolidation and review"])
                groups[i] = [base, suffixes[(i - len(cleaned)) % len(suffixes)]]
        return groups
    for i, topic in enumerate(cleaned):
        groups[min(slots - 1, math.floor(i * slots / len(cleaned)))].append(topic)
    return groups


def _join(items: Iterable[str], sep: str = "; ") -> str:
    return sep.join(x.strip() for x in items if x and x.strip())


def _objective_pair(topic: str, subject: str, ar: bool) -> str:
    if ar:
        return (
            f"يشرح {topic} بدقة.\n"
            f"يطبق {topic} ويبرر خطواته."
        )
    return (
        f"Explain {topic} accurately.\n"
        f"Apply {topic} and justify the method."
    )


def _medium_fallback(meta: dict, topics: list[str], language: str) -> MediumPlan:
    subject = meta.get("subject", "Subject")
    groups = _group_topics(topics, 14, subject, language)
    ar = language == "Arabic"
    weeks: list[MediumWeek] = []
    for group in groups:
        content = _join(group[:3], "؛ " if ar else "; ")
        focus = group[0]
        if ar:
            objectives = _objective_pair(focus, subject, True)
            ai = "يقارن حلّه الأولي بمقترح رقمي، ويتحقق من الدقة ويشرح قراره."
            resources = "الكتاب، أوراق عمل، السبورة التفاعلية، وأداة رقمية معتمدة."
        else:
            objectives = _objective_pair(focus, subject, False)
            ai = "Compare an initial solution with a digital suggestion, verify accuracy, and explain the decision."
            resources = "Textbook, worksheets, interactive board, and an approved digital tool."
        weeks.append(MediumWeek(content=content, learning_objectives=objectives, ai_literacy=ai, resources=resources))

    teacher = meta.get("teacher", "Teacher")
    if ar:
        return MediumPlan(
            title=f"الخطة متوسطة المدى - {subject} - {meta['grade']}",
            targets="تغطية موضوعات الفصل بتسلسل واضح، ورفع مستوى الإتقان، وتنمية التفكير الناقد وحل المشكلات والاستخدام المسؤول للأدوات الرقمية.",
            weeks=weeks,
            assessment_opportunities="تقويم قبلي، أسئلة صفية، مهام أداء، أوراق عمل، اختبارات قصيرة، مراجعة تراكمية، وتقويم ختامي.",
            century_skills="التفكير الناقد، حل المشكلات، التواصل، التعاون، الإبداع، والثقافة الرقمية.",
            vocabulary=_join(clean_topics(topics)[:12], "، "),
            eps_guiding_statement="تعلم عالي الجودة من خلال الاستقصاء والتفكير الناقد والتعاون والتطبيقات الواقعية، مع الالتزام بالمسؤولية والاحترام.",
            global_citizenship="التنمية المستدامة، التواصل الفعال، احترام التنوع، واتخاذ قرارات مسؤولة.",
            cross_curricular="روابط مناسبة مع العلوم والتقنية وتحليل البيانات والاستدامة وفق طبيعة موضوعات المادة.",
            national_identity="المجال: الثقافة والقيم والمواطنة. الأبعاد: الاحترام، الانتماء، التراث، والمحافظة على الموارد.",
            ai_integration_approach="استخدام تعليمي موجه للأدوات المعتمدة في المقارنة والتحقق والتغذية الراجعة، وليس لاستبدال تفكير الطالب.",
            guardrails_prompt_controls="تحديد المهمة بوضوح، استخدام أدوات معتمدة، منع إدخال البيانات الشخصية، ومراجعة المعلم للمخرجات قبل اعتمادها.",
            cognitive_integrity_strategy="يقدم الطالب محاولة أولية ويفسر تفكيره قبل الاستعانة بالأداة الرقمية، ثم يقارن ويصحح ويوثق ما تعلمه.",
            ai_safeguarding="حماية الخصوصية، التحقق من الدقة والتحيز، عدم رفع بيانات أو صور شخصية، والإشارة إلى استخدام المساعدة الرقمية عند الحاجة.",
            compliance=[
                ComplianceItem(area="تكامل المنهج", milestone="تضمين استخدام رقمي هادف مرتبط بأهداف التعلم", responsible_person=teacher, target_date="خلال الفصل", status="قيد التنفيذ"),
                ComplianceItem(area="تدريب الطلبة", milestone="تدريب الطلبة على التحقق وجودة الأوامر والاستخدام المسؤول", responsible_person=teacher, target_date="قبل الأسبوع 4", status="مخطط"),
                ComplianceItem(area="النزاهة المعرفية", milestone="إلزام المحاولة الأولى وشرح التفكير قبل الدعم الرقمي", responsible_person=teacher, target_date="في كل مهمة", status="قيد التنفيذ"),
                ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة وعدم مشاركة بيانات شخصية", responsible_person=teacher, target_date="خلال الفصل", status="قيد التنفيذ"),
            ],
        )
    return MediumPlan(
        title=f"Medium Term Plan - {subject} - {meta['grade']}",
        targets="Cover the term topics in a clear sequence, improve mastery, and develop critical thinking, problem solving, and responsible digital use.",
        weeks=weeks,
        assessment_opportunities="Diagnostic assessment, questioning, performance tasks, worksheets, quizzes, cumulative review, and summative assessment.",
        century_skills="Critical thinking, problem solving, communication, collaboration, creativity, and digital literacy.",
        vocabulary=_join(clean_topics(topics)[:12], ", "),
        eps_guiding_statement="High-quality learning through inquiry, critical thinking, collaboration, real-world application, responsibility, and respect.",
        global_citizenship="Sustainable development, effective communication, valuing diversity, and responsible decision-making.",
        cross_curricular="Relevant links to science, technology, data analysis, and sustainability according to the subject topics.",
        national_identity="Domain: Culture, Values, Citizenship. Dimensions: respect, belonging, heritage, and conservation.",
        ai_integration_approach="Teacher-guided use of approved tools for comparison, verification, and feedback without replacing student thinking.",
        guardrails_prompt_controls="Define the task clearly, use approved tools, enter no personal data, and require teacher review before accepting outputs.",
        cognitive_integrity_strategy="Students submit an initial attempt and explain reasoning before digital support, then compare, correct, and record learning.",
        ai_safeguarding="Protect privacy, verify accuracy and bias, upload no personal data or images, and acknowledge digital assistance where appropriate.",
        compliance=[
            ComplianceItem(area="Curriculum Integration", milestone="Include purposeful digital use linked to learning objectives", responsible_person=teacher, target_date="Throughout term", status="In progress"),
            ComplianceItem(area="Student Training", milestone="Teach verification, prompt quality, and responsible use", responsible_person=teacher, target_date="By Week 4", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Require first attempts and reasoning before digital support", responsible_person=teacher, target_date="Every task", status="In progress"),
            ComplianceItem(area="Privacy & Safety", milestone="Use approved tools and share no personal data", responsible_person=teacher, target_date="Throughout term", status="In progress"),
        ],
    )


def _long_fallback(meta: dict, topics: list[str], language: str) -> LongPlan:
    subject = meta.get("subject", "Subject")
    groups = _group_topics(topics, 6, subject, language)
    titles = ["Autumn 1 (HT1)", "Autumn 2 (HT2)", "Spring 1 (HT3)", "Spring 2 (HT4)", "Summer 1 (HT5)", "Summer 2 (HT6)"]
    ar = language == "Arabic"
    half_terms: list[HalfTerm] = []
    for i, group in enumerate(groups):
        content = "\n".join(f"- {x}" for x in group[:8])
        assessment = "اختبار قصير، مهمة أداء، ومراجعة تراكمية." if ar else "Quiz, performance task, and cumulative review."
        half_terms.append(HalfTerm(title=titles[i], content=content, summative_assessment=assessment))
    teacher = meta.get("teacher", "Teacher")
    if ar:
        compliance = [
            ComplianceItem(area="تكامل المنهج", milestone="ربط الاستخدام الرقمي بأهداف تعلم محددة", responsible_person=teacher, target_date="نهاية HT2", status="مخطط"),
            ComplianceItem(area="تدريب الطلبة", milestone="تدريب الطلبة على الاستخدام الآمن والتحقق من المخرجات", responsible_person=teacher, target_date="نهاية HT3", status="مخطط"),
            ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة الأولى وشرح التفكير قبل الدعم الرقمي", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ"),
            ComplianceItem(area="الخصوصية والسلامة", milestone="عدم مشاركة بيانات شخصية واستخدام أدوات معتمدة", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ"),
        ]
    else:
        compliance = [
            ComplianceItem(area="Curriculum Integration", milestone="Connect digital support to specific learning objectives", responsible_person=teacher, target_date="End of HT2", status="Planned"),
            ComplianceItem(area="Student Training", milestone="Train students in safe use and output verification", responsible_person=teacher, target_date="End of HT3", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Record first attempts and reasoning before digital support", responsible_person=teacher, target_date="Throughout year", status="In progress"),
            ComplianceItem(area="Privacy & Safety", milestone="Use approved tools and share no personal data", responsible_person=teacher, target_date="Throughout year", status="In progress"),
        ]
    return LongPlan(half_terms=half_terms, compliance=compliance)


def _source_prompt(meta: dict, source_text: str, topics: list[str], language: str, instructions: str) -> str:
    topic_block = "\n".join(f"- {x}" for x in clean_topics(topics)[:100])
    # Once clean topics are available, raw source is only a small reference and must never be copied.
    source_reference = source_text[:12_000] if len(topics) < 5 else "Clean topic list is sufficient; do not use raw book prose."
    return f"""
Teacher: {meta.get('teacher')}
Subject: {meta.get('subject')}
Grade group: {meta.get('grade')}
Academic year: {meta.get('academic_year')}
Output language: {language}
Additional instructions: {instructions or 'None'}

AUTHORITATIVE CLEAN CURRICULUM TOPICS:
{topic_block or 'No reliable headings detected. Use neutral foundations, applications, review, and assessment entries rather than copying source prose.'}

Reference only (never copy sentences, legal text, exercises, or publisher information):
{source_reference}
""".strip()


def _shorten_lines(text: str, max_lines: int, max_chars: int) -> str:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" •-–—\t")
        if not line or _is_noise(line):
            continue
        if len(line) > max_chars:
            line = line[: max_chars - 1].rstrip() + "…"
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


def _sanitize_medium(plan: MediumPlan, meta: dict, topics: list[str], language: str) -> MediumPlan:
    fallback = _medium_fallback(meta, topics, language)
    groups = _group_topics(topics, 14, meta.get("subject", "Subject"), language)
    plan.title = _shorten_lines(plan.title, 1, 150) or fallback.title
    plan.targets = _shorten_lines(plan.targets, 2, 260) or fallback.targets
    cleaned_weeks: list[MediumWeek] = []
    for idx in range(14):
        src = plan.weeks[idx] if idx < len(plan.weeks) else fallback.weeks[idx]
        content = _shorten_lines(src.content, 3, 95)
        # Content must be curriculum headings only. Fall back to the clean ordered topics if suspicious.
        if not content or _is_noise(content) or len(content.split()) > 35:
            content = _join(groups[idx][:3], "؛ " if language == "Arabic" else "; ")
        objectives = _shorten_lines(src.learning_objectives, 2, 125) or fallback.weeks[idx].learning_objectives
        ai = _shorten_lines(src.ai_literacy, 2, 135) or fallback.weeks[idx].ai_literacy
        resources = _shorten_lines(src.resources, 2, 135) or fallback.weeks[idx].resources
        cleaned_weeks.append(MediumWeek(content=content, learning_objectives=objectives, ai_literacy=ai, resources=resources))
    plan.weeks = cleaned_weeks
    for field, lines, chars in (
        ("assessment_opportunities", 3, 260), ("century_skills", 2, 220), ("vocabulary", 2, 260),
        ("eps_guiding_statement", 3, 300), ("global_citizenship", 2, 240), ("cross_curricular", 3, 280),
        ("national_identity", 3, 280), ("ai_integration_approach", 3, 300),
        ("guardrails_prompt_controls", 3, 300), ("cognitive_integrity_strategy", 3, 300),
        ("ai_safeguarding", 3, 300),
    ):
        value = _shorten_lines(getattr(plan, field), lines, chars)
        if not value:
            value = getattr(fallback, field)
        setattr(plan, field, value)
    if not plan.compliance:
        plan.compliance = fallback.compliance
    return plan


def _sanitize_long(plan: LongPlan, meta: dict, topics: list[str], language: str) -> LongPlan:
    fallback = _long_fallback(meta, topics, language)
    groups = _group_topics(topics, 6, meta.get("subject", "Subject"), language)
    clean_halves: list[HalfTerm] = []
    for idx in range(6):
        src = plan.half_terms[idx] if idx < len(plan.half_terms) else fallback.half_terms[idx]
        content = _shorten_lines(src.content, 8, 95)
        if not content or _is_noise(content):
            content = "\n".join(f"- {x}" for x in groups[idx][:8])
        assessment = _shorten_lines(src.summative_assessment, 3, 170) or fallback.half_terms[idx].summative_assessment
        clean_halves.append(HalfTerm(title=fallback.half_terms[idx].title, content=content, summative_assessment=assessment))
    plan.half_terms = clean_halves
    if len(plan.compliance) < 4:
        plan.compliance = fallback.compliance
    else:
        plan.compliance = plan.compliance[:4]
    return plan


def generate_medium(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> MediumPlan:
    topics = clean_topics(topics)
    # Use the deterministic planner by default on Render so curriculum generation
    # always completes inside the web request. AI enrichment can be enabled only
    # on a larger instance with CURRICULUM_MEDIUM_AI=1.
    if not _env_flag("CURRICULUM_MEDIUM_AI", False):
        return _sanitize_medium(_medium_fallback(meta, topics, language), meta, topics, language)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _sanitize_medium(_medium_fallback(meta, topics, language), meta, topics, language)
    try:
        from openai import OpenAI

        client = _ai_client(api_key, float(os.getenv("CURRICULUM_GENERATION_TIMEOUT", "45")))
        system = """You are an expert UAE school curriculum planner. Create a Medium Term Plan that exactly fits the supplied EPS template. Produce exactly 14 instructional weeks and no entry for the mid-term break. The Content field may contain ONLY concise unit, chapter, section, or lesson titles from the authoritative clean topic list, normally one to three titles per week. NEVER put publisher names, copyright notices, ISBNs, website addresses, author names, page citations, explanatory paragraphs, examples, questions, worked solutions, or book sentences in Content. If topic evidence is insufficient, write Review, Consolidation, Application, or Assessment rather than inventing or copying prose. Write exactly two measurable Bloom-aligned learning objectives per week. Keep all cells concise for a landscape Word table. Include purposeful subject-specific resources, assessment, UAE national identity, sustainability, cross-curricular links, and safe responsible AI use. Output only the structured plan."""
        response = client.responses.parse(
            model=os.getenv("CURRICULUM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini")),
            input=[{"role": "system", "content": system}, {"role": "user", "content": _source_prompt(meta, source_text, topics, language, instructions)}],
            text_format=MediumPlan,
        )
        plan = response.output_parsed
        if not plan or len(plan.weeks) != 14:
            raise ValueError("AI returned an invalid number of weeks")
        return _sanitize_medium(plan, meta, topics, language)
    except Exception as exc:
        logger.warning("Medium plan AI generation fell back to deterministic planning: %s", exc)
        return _sanitize_medium(_medium_fallback(meta, topics, language), meta, topics, language)


def generate_long(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> LongPlan:
    topics = clean_topics(topics)
    # Long-term mapping is generated locally by default. This is accurate, immediate, and
    # prevents Render 502 errors caused by a second long structured AI request. Set
    # CURRICULUM_LONG_AI=1 only on a larger paid instance when AI enrichment is required.
    if not _env_flag("CURRICULUM_LONG_AI", False):
        return _sanitize_long(_long_fallback(meta, topics, language), meta, topics, language)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _sanitize_long(_long_fallback(meta, topics, language), meta, topics, language)
    try:
        client = _ai_client(api_key, float(os.getenv("CURRICULUM_GENERATION_TIMEOUT", "45")))
        system = """You are an expert UAE school curriculum planner. Create a full-year Long Term Plan for the supplied EPS template. Produce exactly six half-terms in this order: Autumn 1, Autumn 2, Spring 1, Spring 2, Summer 1, Summer 2. Each content cell may contain ONLY concise unit and lesson titles from the authoritative clean topic list. Never include copyright, publisher, ISBN, websites, page references, examples, exercises, questions, solutions, or explanatory book paragraphs. Distribute the supplied curriculum logically, include concise summative assessment opportunities, and provide exactly four implementation/compliance rows covering curriculum integration, student training, cognitive integrity, and privacy/safety. Output only the structured plan."""
        response = client.responses.parse(
            model=os.getenv("CURRICULUM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini")),
            input=[{"role": "system", "content": system}, {"role": "user", "content": _source_prompt(meta, source_text, topics, language, instructions)}],
            text_format=LongPlan,
        )
        plan = response.output_parsed
        if not plan or len(plan.half_terms) != 6:
            raise ValueError("AI returned an invalid number of half-terms")
        return _sanitize_long(plan, meta, topics, language)
    except Exception as exc:
        logger.warning("Long plan AI generation fell back to deterministic planning: %s", exc)
        return _sanitize_long(_long_fallback(meta, topics, language), meta, topics, language)
