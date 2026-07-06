from __future__ import annotations

import base64
import io
import os
import re
import unicodedata
from pathlib import Path

from curriculum_models import ComplianceItem, MediumPlan, MediumWeek, TopicExtraction

BAD_GLYPHS = re.compile(r"[�□■▢▣▤▥▦▧▨▩]+")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
WORD_RE = re.compile(r"[A-Za-z\u0600-\u06ff0-9]+")


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = CONTROL.sub(" ", text)
    text = BAD_GLYPHS.sub(" ", text)
    text = text.replace("\uf0b7", "•").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_line(value: str) -> str:
    text = _normalise(value)
    text = re.sub(r"^\s*\[HEADING\]\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*[•▪◦●✓✔-]+\s*", "", text)
    text = re.sub(r"\.{2,}\s*\d+\s*$", "", text)
    text = re.sub(r"\s+(?:page|p\.?|صفحة)\s*\d+\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -–—|:;,.•")
    return text


def _bad_ratio(text: str) -> float:
    raw = str(text or "")
    if not raw:
        return 1.0
    bad = len(BAD_GLYPHS.findall(raw)) + raw.count("�")
    return bad / max(len(raw), 1)


def _valid_topic(value: str) -> bool:
    text = _clean_line(value)
    if not text or _bad_ratio(value) > 0.01:
        return False
    words = WORD_RE.findall(text)
    if not 1 <= len(words) <= 16 or len(text) > 130:
        return False
    low = text.casefold()
    noise = (
        "copyright", "publisher", "isbn", "all rights", "www.", "http", "example",
        "exercise", "solution", "حقوق الطبع", "الناشر", "مثال", "تمرين", "الحل",
        "إجابة", "answer key", "teacher edition", "student edition",
    )
    if any(item in low for item in noise):
        return False
    if re.fullmatch(r"[\d\W_]+", text):
        return False
    return True


def _dedupe(values: list[str], limit: int = 70) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_line(value)
        if not _valid_topic(text):
            continue
        key = re.sub(r"[^A-Za-z0-9\u0600-\u06ff]+", "", text.casefold())
        if not key or key in seen:
            continue
        if any(min(len(key), len(old)) >= 12 and (key in old or old in key) for old in seen):
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _language(value: str) -> str:
    return "Arabic" if str(value or "").strip().casefold() in {"arabic", "ar", "العربية", "عربي"} else "English"


def _subject(value: str, language: str) -> str:
    raw = _normalise(value)
    low = raw.casefold()
    families = [
        (("chemistry", "كيمياء", "الكيمياء"), "الكيمياء", "Chemistry"),
        (("mathematics", "math", "رياضيات", "الرياضيات"), "الرياضيات", "Mathematics"),
        (("physics", "فيزياء", "الفيزياء"), "الفيزياء", "Physics"),
        (("biology", "أحياء", "الاحياء", "الأحياء"), "الأحياء", "Biology"),
        (("science", "علوم", "العلوم"), "العلوم", "Science"),
    ]
    for aliases, ar, en in families:
        if any(alias in low for alias in aliases):
            return ar if language == "Arabic" else en
    if language == "Arabic":
        return re.sub(r"[A-Za-z]+", "", raw).strip(" -–—/") or "المادة"
    return re.sub(r"[\u0600-\u06ff]+", "", raw).strip(" -–—/") or "Subject"


def _grade(value: str, language: str) -> str:
    from curriculum_ai import localize_grade
    return _normalise(localize_grade(value, language))


def _plain_lines(text: str) -> list[str]:
    output: list[str] = []
    for raw in _normalise(text).splitlines():
        line = _clean_line(raw)
        if line:
            output.append(line)
    return output


def _candidate_topics(source_text: str, manual_topics: str = "") -> list[str]:
    values: list[str] = []
    for raw in re.split(r"[\n;]+", manual_topics or ""):
        values.append(raw)
    values.extend(_plain_lines(source_text))
    return _dedupe(values)


def _pdf_page_images(path: Path, pages: list[int]) -> list[str]:
    import fitz
    from PIL import Image

    urls: list[str] = []
    with fitz.open(path) as pdf:
        for page_no in pages[:8]:
            if not 0 <= page_no < len(pdf):
                continue
            pix = pdf[page_no].get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            image.thumbnail((1600, 2100))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=82, optimize=True)
            urls.append("data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"))
    return urls


def _likely_contents_pages(path: Path) -> list[int]:
    import fitz

    found: list[int] = []
    with fitz.open(path) as pdf:
        max_pages = min(len(pdf), 36)
        for page_no in range(max_pages):
            try:
                text = _normalise(pdf[page_no].get_text("text", sort=True))
            except Exception:
                text = ""
            low = text.casefold()
            score = sum(token in low for token in (
                "contents", "table of contents", "unit", "chapter", "lesson",
                "المحتويات", "الفهرس", "الوحدة", "الفصل", "الدرس",
            ))
            short_lines = sum(1 for line in text.splitlines() if 2 <= len(line.split()) <= 12)
            if score >= 2 or (score >= 1 and short_lines >= 8):
                found.append(page_no)
        if not found:
            found = list(range(min(len(pdf), 10)))
    return found[:8]


def _vision_pdf_topics(path: Path, language: str, subject: str, grade: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI

        images = _pdf_page_images(path, _likely_contents_pages(path))
        if not images:
            return ""
        target = "Arabic only" if language == "Arabic" else "English only"
        content = [{
            "type": "input_text",
            "text": (
                f"These are likely contents pages from a {subject} textbook for {grade}. "
                f"Extract the exact ordered unit, chapter, section, and lesson titles visible in the images. "
                f"Return one title per line in {target}. Remove page numbers, publishers, examples, exercises, "
                "copyright text, assessment labels, and OCR noise. Do not invent any topic."
            ),
        }]
        content.extend({"type": "input_image", "image_url": url} for url in images)
        client = OpenAI(api_key=api_key, timeout=28.0, max_retries=0)
        response = client.responses.create(
            model=os.getenv("CURRICULUM_VISION_MODEL", "gpt-4.1-mini"),
            input=[{"role": "user", "content": content}],
            max_output_tokens=2200,
            store=False,
        )
        return _normalise(getattr(response, "output_text", "") or "")
    except Exception:
        return ""


def robust_extract(path: Path) -> str:
    from curriculum_extractors import extract_text

    path = Path(path)
    text = ""
    try:
        text = _normalise(extract_text(path))
    except Exception:
        text = ""

    candidates = _candidate_topics(text)
    if path.suffix.lower() == ".pdf" and (len(candidates) < 6 or _bad_ratio(text) > 0.005):
        language = "Arabic"
        vision = _vision_pdf_topics(path, language, "المادة", "الصف")
        if vision:
            return vision
    return text


def professional_refine(meta: dict, source_text: str, candidates: list[str], language: str) -> list[str]:
    language = _language(language)
    subject = _subject(meta.get("subject", ""), language)
    grade = _grade(meta.get("grade", ""), language)
    base = _dedupe(list(candidates) + _plain_lines(source_text))

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and base:
        try:
            from openai import OpenAI

            target = "Arabic only" if language == "Arabic" else "English only"
            client = OpenAI(api_key=api_key, timeout=26.0, max_retries=0)
            response = client.responses.parse(
                model=os.getenv("CURRICULUM_MODEL", "gpt-4.1-mini"),
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a curriculum extraction specialist. Return only exact ordered unit and lesson titles "
                            "that are supported by the uploaded source. Remove OCR corruption, box symbols, page numbers, "
                            "publishers, examples, exercises, assessments, prose, and duplicate fragments. Never invent "
                            f"textbook content. Translate retained titles into {target} and never mix languages."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Subject: {subject}\nGrade: {grade}\n\nDetected source lines:\n" +
                            "\n".join(f"- {item}" for item in base[:80])
                        ),
                    },
                ],
                text_format=TopicExtraction,
            )
            parsed = response.output_parsed
            result = _dedupe(parsed.topics if parsed else [])
            if len(result) >= 4:
                return result
        except Exception:
            pass

    result = _dedupe(base)
    if language == "Arabic":
        result = [item for item in result if ARABIC_RE.search(item)]
    else:
        result = [item for item in result if not ARABIC_RE.search(item)]
    return result


def _topic_words(topic: str) -> set[str]:
    stop = {"في", "من", "إلى", "على", "عن", "the", "of", "and", "to", "a", "an"}
    return {word.casefold() for word in WORD_RE.findall(topic) if len(word) > 2 and word.casefold() not in stop}


def _week_grounded(week: MediumWeek, topics: list[str]) -> bool:
    content_words = _topic_words(week.content)
    return any(content_words & _topic_words(topic) for topic in topics)


def _clean_plan(plan: MediumPlan, language: str) -> MediumPlan:
    data = plan.model_dump()

    def clean(value: str) -> str:
        text = _normalise(value)
        text = BAD_GLYPHS.sub(" ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = clean(value)
    for week in data.get("weeks", []):
        for key in ("content", "learning_objectives", "ai_literacy", "resources"):
            week[key] = clean(week.get(key, ""))
    for item in data.get("compliance", []):
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = clean(value)
    return MediumPlan.model_validate(data)


def _chemistry_objectives(topic: str, language: str) -> str:
    if language == "Arabic":
        return (
            f"• يفسر المفاهيم والتمثيلات الكيميائية المرتبطة بـ {topic} مستخدمًا المصطلحات العلمية الدقيقة.\n"
            f"• يطبق المعرفة المرتبطة بـ {topic} في تفسير البيانات أو كتابة المعادلات أو إجراء الحسابات المناسبة مع التحقق من الناتج."
        )
    return (
        f"• Explain the chemical concepts and representations in {topic} using accurate scientific terminology.\n"
        f"• Apply knowledge of {topic} to interpret evidence, write equations, or complete relevant calculations and verify the result."
    )


def _generic_objectives(topic: str, language: str) -> str:
    if language == "Arabic":
        return (
            f"• يفسر المفاهيم والعلاقات الأساسية في {topic} باستخدام تمثيل مناسب ومصطلحات دقيقة.\n"
            f"• يطبق المعرفة والمهارات المرتبطة بـ {topic} في مهمة جديدة ويبرر خطواته ويتحقق من النتيجة."
        )
    return (
        f"• Explain the central concepts and relationships in {topic} using an appropriate representation and precise terminology.\n"
        f"• Apply the knowledge and skills of {topic} to a new task, justify the process, and verify the result."
    )


def _resources(subject: str, topic: str, language: str, index: int) -> str:
    chemistry = "chem" in subject.casefold() or "كيمياء" in subject
    if language == "Arabic":
        if chemistry:
            options = [
                "الكتاب المدرسي، الجدول الدوري، نماذج جزيئية، ورقة عمل متدرجة، والسبورة التفاعلية.",
                "الكتاب المدرسي، بيانات أو رسوم بيانية، آلة حاسبة علمية، محاكاة PhET معتمدة، وبطاقة تحقق.",
                "الكتاب المدرسي، أدوات مختبر آمنة عند ملاءمة الموضوع، صحيفة ملاحظات، وعرض بصري للتمثيل الجسيمي.",
            ]
        else:
            options = [
                "الكتاب المدرسي، أمثلة مختارة، ورقة عمل متدرجة، السبورة التفاعلية، وبطاقة خروج.",
                "الكتاب المدرسي، تمثيل بصري أو بيانات، أداة رقمية معتمدة، ومهمة تطبيقية قصيرة.",
            ]
    else:
        if chemistry:
            options = [
                "Textbook, periodic table, molecular models, graduated worksheet, and interactive board.",
                "Textbook, data or graphs, scientific calculator, approved PhET simulation, and checking card.",
                "Textbook, safe laboratory equipment where appropriate, observation sheet, and particle-model visual.",
            ]
        else:
            options = [
                "Textbook, selected examples, graduated worksheet, interactive board, and exit ticket.",
                "Textbook, a visual or data set, an approved digital tool, and a short applied task.",
            ]
    return options[index % len(options)]


def _ai_objective(language: str, index: int) -> str:
    ar = [
        "يقارن الطالب تفسيره المستقل بمخرج رقمي، ثم يتحقق من الدقة باستخدام دليل من الكتاب أو البيانات.",
        "يصمم الطالب أمرًا رقميًا محددًا للمهمة، ويحدد المعلومات الناقصة قبل استخدام الأداة المعتمدة.",
        "يكتشف الطالب خطأً أو مبالغة في مخرج رقمي ويصححه بالاستناد إلى المفهوم العلمي والأدلة.",
        "يوثق الطالب ما عدله بعد التغذية الراجعة الرقمية دون مشاركة أسماء أو صور أو بيانات شخصية.",
    ]
    en = [
        "Compare an independent explanation with a digital output and verify accuracy using textbook or data evidence.",
        "Design a focused prompt for the task and identify missing information before using an approved tool.",
        "Detect an error or overclaim in a digital output and correct it using scientific concepts and evidence.",
        "Document revisions after digital feedback without sharing names, images, or personal data.",
    ]
    return (ar if language == "Arabic" else en)[index % 4]


def _fallback_medium(meta: dict, topics: list[str], language: str) -> MediumPlan:
    subject = _subject(meta.get("subject", ""), language)
    grade = _grade(meta.get("grade", ""), language)
    chemistry = "chem" in subject.casefold() or "كيمياء" in subject
    ordered = topics[:]
    weeks: list[MediumWeek] = []
    for index in range(14):
        topic = ordered[min(index, len(ordered) - 1)] if index < len(ordered) else ordered[index % len(ordered)]
        if index >= len(ordered):
            if language == "Arabic":
                topic = f"مراجعة مترابطة وتطبيقات على {topic}"
            else:
                topic = f"Connected review and applications of {topic}"
        objectives = _chemistry_objectives(topic, language) if chemistry else _generic_objectives(topic, language)
        weeks.append(MediumWeek(
            content=f"• {topic}",
            learning_objectives=objectives,
            ai_literacy=_ai_objective(language, index),
            resources=_resources(subject, topic, language, index),
        ))

    teacher = str(meta.get("teacher", "")).strip() or ("المعلم" if language == "Arabic" else "Teacher")
    if language == "Arabic":
        return MediumPlan(
            title=f"الخطة متوسطة المدى - {subject} - {grade}",
            targets=(
                "بناء فهم متدرج ودقيق لمحتوى الفصل، ربط التمثيلات والمفاهيم بالأدلة، تنمية مهارات الاستقصاء والحساب وتحليل البيانات، "
                "وتوظيف التقويم التكويني والتغذية الراجعة لرفع مستوى الإتقان بصورة واقعية قابلة للقياس."
            ),
            weeks=weeks,
            assessment_opportunities="تقويم تشخيصي، ملاحظات عملية، أسئلة صفية موجهة، أوراق عمل متدرجة، اختبارات قصيرة، تحليل أخطاء، مهمة أداء، ومراجعة ختامية قائمة على بيانات الإتقان.",
            century_skills="التفكير الناقد، حل المشكلات، التواصل العلمي، التعاون، تحليل البيانات، الثقافة الرقمية، وإدارة التعلم.",
            vocabulary="، ".join(topics[:12]),
            eps_guiding_statement="تعلم عالي الجودة قائم على الاستقصاء والدليل والتفكير الناقد والتعاون والتغذية الراجعة والتطبيق الواقعي المسؤول.",
            global_citizenship="تفسير القضايا العلمية المرتبطة بالصحة والبيئة والاستدامة واتخاذ قرارات مسؤولة قائمة على الأدلة.",
            cross_curricular="روابط واقعية مع الرياضيات وتحليل البيانات والفيزياء والأحياء والاستدامة وفق موضوعات الفصل.",
            national_identity="ربط التعلم بالأمن العلمي والاستدامة والمحافظة على الموارد والابتكار في دولة الإمارات مع احترام القيم والمسؤولية.",
            ai_integration_approach="استخدام موجه للأدوات المعتمدة في التمثيل والتحقق وتحليل البيانات والتغذية الراجعة بعد محاولة الطالب المستقلة.",
            guardrails_prompt_controls="استخدام أوامر محددة مرتبطة بهدف التعلم، منع البيانات الشخصية، تقييد الأداة بالمصادر المعتمدة، والتحقق من كل مخرج قبل اعتماده.",
            cognitive_integrity_strategy="يقدم الطالب محاولة مستقلة وتفسيرًا أوليًا قبل الدعم الرقمي، ثم يقارن ويصحح ويوثق ما تعلمه دون نقل الإجابة.",
            ai_safeguarding="حماية الخصوصية، عدم رفع أسماء أو صور، فحص الدقة والتحيز، استخدام أدوات المدرسة المعتمدة، والإفصاح عن المساعدة الرقمية.",
            compliance=[
                ComplianceItem(area="تكامل المنهج", milestone="ربط الاستخدام الرقمي بهدف تعلم واضح ومحتوى الأسبوع", responsible_person=teacher, target_date="طوال الفصل", status="قيد التنفيذ"),
                ComplianceItem(area="تدريب الطلبة", milestone="تطبيق روتين التحقق من الدقة والمصدر قبل اعتماد المخرج", responsible_person=teacher, target_date="قبل الأسبوع الرابع", status="مخطط"),
                ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة المستقلة قبل استخدام الأداة", responsible_person=teacher, target_date="كل مهمة", status="قيد التنفيذ"),
                ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة دون بيانات شخصية", responsible_person=teacher, target_date="طوال الفصل", status="قيد التنفيذ"),
            ],
        )
    return MediumPlan(
        title=f"Medium Term Plan - {subject} - {grade}",
        targets="Build coherent mastery of term content, connect concepts and representations to evidence, develop inquiry, calculation, and data-analysis skills, and use formative assessment to improve measurable outcomes.",
        weeks=weeks,
        assessment_opportunities="Diagnostic assessment, practical observations, targeted questioning, graduated worksheets, quizzes, error analysis, a performance task, and a mastery-informed final review.",
        century_skills="Critical thinking, problem solving, scientific communication, collaboration, data analysis, digital literacy, and self-management.",
        vocabulary=", ".join(topics[:12]),
        eps_guiding_statement="High-quality learning through inquiry, evidence, critical thinking, collaboration, feedback, responsible action, and real-world application.",
        global_citizenship="Use scientific evidence to understand health, environmental, and sustainability issues and make responsible decisions.",
        cross_curricular="Purposeful links with mathematics, data analysis, physics, biology, and sustainability according to the term topics.",
        national_identity="Connect learning to innovation, sustainability, conservation, and responsible citizenship in the UAE.",
        ai_integration_approach="Teacher-guided use of approved tools for representation, verification, data analysis, and feedback after an independent attempt.",
        guardrails_prompt_controls="Use task-specific prompts, approved sources, no personal data, and mandatory verification before accepting any output.",
        cognitive_integrity_strategy="Students submit and explain an independent first attempt before digital support, then compare, correct, and document learning.",
        ai_safeguarding="Protect privacy, upload no names or images, check accuracy and bias, use approved tools, and acknowledge digital assistance.",
        compliance=[
            ComplianceItem(area="Curriculum Integration", milestone="Link every digital use to a clear learning objective and weekly content", responsible_person=teacher, target_date="Throughout Term", status="In Progress"),
            ComplianceItem(area="Student Training", milestone="Establish an accuracy and source-verification routine", responsible_person=teacher, target_date="By Week Four", status="Planned"),
            ComplianceItem(area="Cognitive Integrity", milestone="Document an independent first attempt", responsible_person=teacher, target_date="Every Task", status="In Progress"),
            ComplianceItem(area="Privacy and Safety", milestone="Use approved tools without personal data", responsible_person=teacher, target_date="Throughout Term", status="In Progress"),
        ],
    )


def professional_generate_medium(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> MediumPlan:
    language = _language(language)
    meta["language"] = language
    meta["subject"] = _subject(meta.get("subject", ""), language)
    meta["grade"] = _grade(meta.get("grade", ""), language)
    topics = _dedupe(topics)
    if len(topics) < 4:
        raise ValueError("لم تُقرأ موضوعات كافية من الملف. ارفع صفحات الفهرس أو الصق عناوين الوحدات والدروس بوضوح.")

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI

            target = "Arabic only" if language == "Arabic" else "English only"
            teacher = str(meta.get("teacher", "")).strip()
            client = OpenAI(api_key=api_key, timeout=35.0, max_retries=0)
            response = client.responses.parse(
                model=os.getenv("CURRICULUM_MODEL", "gpt-4.1-mini"),
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior curriculum leader in a UAE private school. Create a realistic, precise, "
                            "implementation-ready Medium Term Plan for exactly 14 instructional weeks. Ground every week "
                            "in the supplied textbook topics and preserve their order. Do not invent textbook units or use "
                            "generic placeholders such as core concepts, key knowledge, or applied skills. Use subject-specific "
                            "objectives, varied assessment evidence, and realistic resources. Every field must be in " + target +
                            ". Remove OCR noise and never output square boxes, replacement characters, mojibake, or mixed-language titles. "
                            "For chemistry, use accurate scientific language and include equations, calculations, particle models, data, "
                            "practical investigation, and safety only where the supplied topic makes them relevant. AI literacy must support "
                            "independent thinking and verification, not replace subject learning."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Teacher: {teacher}\nSubject: {meta['subject']}\nGrade: {meta['grade']}\n"
                            f"Academic year: {meta.get('academic_year', '2026-2027')}\nAdditional instructions: {instructions or 'None'}\n\n"
                            "Ordered textbook topics (use only these or faithful combinations of them):\n" +
                            "\n".join(f"{index}. {topic}" for index, topic in enumerate(topics[:40], 1))
                        ),
                    },
                ],
                text_format=MediumPlan,
            )
            parsed = response.output_parsed
            if parsed and len(parsed.weeks) == 14:
                cleaned = _clean_plan(parsed, language)
                grounded = sum(_week_grounded(week, topics) for week in cleaned.weeks)
                if grounded >= 10 and not any(_bad_ratio(week.content) for week in cleaned.weeks):
                    return cleaned
        except Exception:
            pass

    return _clean_plan(_fallback_medium(meta, topics, language), language)


def install(core) -> None:
    core.extract_curriculum_text = robust_extract
    core.candidate_topics = _candidate_topics
    core.refine_topics = professional_refine
    core.generate_medium = professional_generate_medium
