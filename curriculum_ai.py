from __future__ import annotations

import logging
import os
import re

from curriculum_models import ComplianceItem, HalfTerm, LongPlan, MediumPlan, MediumWeek, TopicExtraction

logger = logging.getLogger("magdy_lesson_planner.curriculum")

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
NOISE = (
    "copyright", "all rights reserved", "mcgraw", "pearson", "publisher", "publishing",
    "isbn", "sourced from", "education, llc", "trademark", "teacher edition", "www.",
    "http://", "https://", "©", "®", "™", "example", "exercise", "solution", "figure",
    "warning", "page", "differentiation", "حقوق الطبع", "جميع الحقوق محفوظة", "الناشر",
    "الطبعة", "حقوق النشر", "المصدر", "مثال", "تمرين", "الحل", "الشكل", "تحذير", "صفحة",
)
GENERIC = {"unit", "chapter", "lesson", "section", "module", "topic", "الوحدة", "الفصل", "الدرس", "الباب", "الموضوع"}

AR_TO_EN = {
    "النهايات والاتصال": "Limits and Continuity", "النهايات": "Limits", "الاتصال": "Continuity",
    "التفاضل": "Differentiation", "الاشتقاق": "Differentiation", "المشتقات": "Derivatives",
    "المماسات والسرعة المتجهة": "Tangents and Velocity", "المماسات": "Tangents",
    "السرعة المتجهة": "Velocity", "التكامل": "Integration", "التكاملات": "Integrals",
    "الدوال الأسية واللوغاريتمية": "Exponential and Logarithmic Functions",
    "الدوال المثلثية": "Trigonometric Functions", "المتجهات": "Vectors", "المصفوفات": "Matrices",
    "القطوع المخروطية": "Conic Sections", "الإحصاء والاحتمال": "Statistics and Probability",
    "المعادلات التفاضلية": "Differential Equations", "الدوال": "Functions",
    "خطوط التقارب": "Asymptotes", "القيم القصوى": "Extrema", "قاعدة السلسلة": "Chain Rule",
    "قاعدة الضرب والقسمة": "Product and Quotient Rules", "المساحة بين منحنيين": "Area Between Curves",
    "الحجوم": "Volumes", "التكامل المحدد": "Definite Integrals", "تطبيقات المشتقات": "Applications of Derivatives",
}
EN_TO_AR = {v.casefold(): k for k, v in AR_TO_EN.items()}


def normalize_language(value: str) -> str:
    return "Arabic" if str(value or "").strip().casefold() in {"arabic", "ar", "العربية", "عربي"} else "English"




def localize_subject(value: str, language: str) -> str:
    """Return the subject name in the selected output language."""
    language = normalize_language(language)
    raw = str(value or "").strip()
    low = raw.casefold()
    if language == "Arabic":
        mapping = {
            "mathematics": "الرياضيات", "math": "الرياضيات", "calculus": "حساب التفاضل والتكامل",
            "physics": "الفيزياء", "chemistry": "الكيمياء", "biology": "الأحياء",
            "science": "العلوم", "english": "اللغة الإنجليزية", "arabic": "اللغة العربية",
            "computer science": "علوم الحاسوب", "business": "إدارة الأعمال",
        }
        if re.search(r"[\u0600-\u06ff]", raw):
            return raw
        return mapping.get(low, raw)
    mapping = {
        "الرياضيات": "Mathematics", "رياضيات": "Mathematics", "حساب التفاضل والتكامل": "Calculus",
        "الفيزياء": "Physics", "الكيمياء": "Chemistry", "الأحياء": "Biology",
        "العلوم": "Science", "اللغة الإنجليزية": "English", "اللغة العربية": "Arabic",
        "علوم الحاسوب": "Computer Science", "إدارة الأعمال": "Business",
    }
    if not re.search(r"[\u0600-\u06ff]", raw):
        return raw
    for ar, en in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        if ar in raw:
            return en
    return "Subject"


def localize_grade(value: str, language: str) -> str:
    """Return a clean grade label in the selected output language."""
    language = normalize_language(language)
    raw = str(value or "").strip()
    low = raw.casefold()
    ar_ord = {
        "الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5, "السادس": 6,
        "السابع": 7, "الثامن": 8, "التاسع": 9, "العاشر": 10, "الحادي عشر": 11, "الثاني عشر": 12,
    }
    number = None
    match = re.search(r"(?:grade|gr\.?|الصف)?\s*(1[0-2]|[1-9])", low)
    if match:
        number = int(match.group(1))
    if number is None:
        for label, num in sorted(ar_ord.items(), key=lambda item: len(item[0]), reverse=True):
            if label in raw:
                number = num
                break
    advanced = any(x in low for x in ("advanced", "adv", "متقدم"))
    general = any(x in low for x in ("general", "عام"))
    if language == "English":
        if number:
            suffix = " Advanced" if advanced else (" General" if general else "")
            return f"Grade {number}{suffix}"
        return raw if raw and not re.search(r"[\u0600-\u06ff]", raw) else "Grade Group"
    arabic_numbers = {1:"الأول",2:"الثاني",3:"الثالث",4:"الرابع",5:"الخامس",6:"السادس",7:"السابع",8:"الثامن",9:"التاسع",10:"العاشر",11:"الحادي عشر",12:"الثاني عشر"}
    if number:
        suffix = " متقدم" if advanced else (" عام" if general else "")
        return f"{arabic_numbers[number]}{suffix}"
    return raw if raw and re.search(r"[\u0600-\u06ff]", raw) else "الصف"


def _has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(text or "")))


def _clean_topic(text: str) -> str:
    text = str(text or "").translate(ARABIC_DIGITS)
    text = re.sub(r"^\s*\[HEADING\]\s*", "", text, flags=re.I)
    labels = r"unit|chapter|lesson|section|module|topic|الوحدة|الفصل|الدرس|الباب|الموضوع"
    text = re.sub(rf"^\s*(?:{labels})\s*(?:رقم|no\.?)?\s*\d+(?:[.\-]\d+)*\s*[:\-–—|]*\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d+(?:[.\-]\d+){1,3}\s*[:\-–—|]*\s*", "", text)
    text = re.sub(r"\.{2,}\s*\d+\s*$", "", text)
    text = re.sub(r"(?<![A-Za-z])\b\d+(?:[.\-]\d+)*\b(?![A-Za-z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" •-–—|:;,.")
    low = text.casefold()
    if not text or low in GENERIC or any(term in low for term in NOISE):
        return ""
    if len(text) > 105 or not 1 <= len(text.split()) <= 13:
        return ""
    if sum(ch.isdigit() for ch in text) > 1 or sum(ch in "+=<>[]{}()" for ch in text) >= 3:
        return ""
    if re.search(r"[.!?؟؛]$", text):
        return ""
    return text


def clean_topics(topics: list[str], limit: int = 90) -> list[str]:
    out: list[str] = []
    keys: list[str] = []
    for raw in topics:
        topic = _clean_topic(raw)
        if not topic:
            continue
        key = re.sub(r"[^\w\u0600-\u06ff]+", "", topic.casefold())
        if not key or any(key == old or (min(len(key), len(old)) >= 10 and (key in old or old in key)) for old in keys):
            continue
        keys.append(key)
        out.append(topic)
        if len(out) >= limit:
            break
    return out


def _known_translate(title: str, language: str) -> str:
    language = normalize_language(language)
    value = _clean_topic(title)
    if not value:
        return ""
    if language == "Arabic":
        if _has_arabic(value):
            return value
        low = value.casefold()
        if low in EN_TO_AR:
            return EN_TO_AR[low]
        for en, ar in sorted(EN_TO_AR.items(), key=lambda x: len(x[0]), reverse=True):
            if en in low:
                return ar
        return ""
    if not _has_arabic(value):
        return value
    if value in AR_TO_EN:
        return AR_TO_EN[value]
    for ar, en in sorted(AR_TO_EN.items(), key=lambda x: len(x[0]), reverse=True):
        if ar in value:
            return en
    return ""


def _localize(topics: list[str], language: str) -> list[str]:
    return clean_topics([x for x in (_known_translate(t, language) for t in clean_topics(topics)) if x])


def _defaults(meta: dict, language: str) -> list[str]:
    is_math = "math" in str(meta.get("subject", "")).casefold() or "رياض" in str(meta.get("subject", ""))
    if normalize_language(language) == "Arabic":
        return (["المفاهيم الأساسية", "التمثيلات الرياضية", "الاستراتيجيات الجبرية", "حل المشكلات", "التطبيقات الواقعية", "المراجعة والتقويم"]
                if is_math else ["المفاهيم الأساسية", "المعرفة الرئيسة", "المهارات التطبيقية", "التحليل والاستقصاء", "المشروع التطبيقي", "المراجعة والتقويم"])
    return (["Core Concepts", "Mathematical Representations", "Algebraic Strategies", "Problem Solving", "Real-World Applications", "Review and Assessment"]
            if is_math else ["Core Concepts", "Key Knowledge", "Applied Skills", "Analysis and Inquiry", "Applied Project", "Review and Assessment"])


def refine_topics(meta: dict, source_text: str, candidates: list[str], language: str) -> list[str]:
    language = normalize_language(language)
    base = clean_topics(candidates)
    if not base:
        return _defaults(meta, language)
    localized = _localize(base, language)
    target_ok = all((_has_arabic(x) if language == "Arabic" else not _has_arabic(x)) for x in base)
    if target_ok and localized:
        return localized

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=float(os.getenv("CURRICULUM_REFINE_TIMEOUT", "12")), max_retries=0)
            target = "Arabic only" if language == "Arabic" else "English only"
            response = client.responses.parse(
                model=os.getenv("CURRICULUM_MODEL", "gpt-4.1-mini"),
                input=[
                    {"role": "system", "content": "Extract only genuine ordered curriculum unit and lesson titles. Remove numbering, publishers, copyright, pages, examples, exercises, equations, prose, figures and fragments. Translate every retained title into " + target + ". Never mix languages and never invent content."},
                    {"role": "user", "content": f"Subject: {meta.get('subject')}\nGrade: {meta.get('grade')}\n\n" + "\n".join(f"- {x}" for x in base[:70])},
                ],
                text_format=TopicExtraction,
            )
            parsed = response.output_parsed
            result = _localize(parsed.topics if parsed else [], language)
            if result:
                return result
        except Exception as exc:
            logger.warning("Curriculum title translation failed: %s", exc)
    return localized or _defaults(meta, language)


def _core(text: str, language: str) -> str:
    value = _clean_topic(text) or ("الموضوع" if normalize_language(language) == "Arabic" else "the topic")
    return value


def _is_math(subject: str) -> bool:
    low = str(subject or "").casefold()
    return "math" in low or "calculus" in low or "رياض" in low or "حساب" in low


def _math_items(topic: str, language: str) -> list[str]:
    ar = normalize_language(language) == "Arabic"
    t = topic.casefold()
    if any(k in t for k in ["limit", "نهايات", "نهاية", "continuity", "اتصال"]):
        return (["مراجعة الدوال والتمثيلات البيانية والسلوك المحلي", "مفهوم النهاية وتقديرها عددياً وبيانياً", "حساب النهايات بالتعويض المباشر والتحليل والاختصار", "حساب النهايات بتوحيد المقامات والأساليب الجبرية", "النهايات عند اللانهاية والسلوك الطرفي", "النهايات غير المنتهية وخطوط التقارب الرأسية", "الاستمرارية على نقطة وفترة وتحديد نقاط عدم الاتصال", "تطبيق نظرية القيمة المتوسطة وتحليل التمثيلات"] if ar else
                ["Review of functions, graphs, and local behavior", "Concept of a limit using tables and graphs", "Evaluate limits by direct substitution, factorisation, and cancellation", "Evaluate limits using algebraic simplification and common denominators", "Limits at infinity and end behavior", "Infinite limits and vertical asymptotes", "Continuity at a point and on an interval", "Intermediate Value Theorem and multi-representation analysis"])
    if any(k in t for k in ["derivative", "different", "اشتقاق", "تفاضل", "مشتق", "tangent", "مماس"]):
        return (["مفهوم المشتقة من خلال معدل التغير وميل المماس", "تقدير المشتقة عددياً وبيانياً", "قواعد اشتقاق القوى والثوابت والمجاميع", "قاعدتا الضرب والقسمة", "قاعدة السلسلة ومشتقات الدوال المركبة", "المشتقات الضمنية ومشتقات الدوال المثلثية", "القيم القصوى وفترات التزايد والتناقص", "تطبيقات المشتقات في الحركة والتحسين ورسم المنحنيات"] if ar else
                ["Derivative as rate of change and tangent slope", "Estimate derivatives numerically and graphically", "Power, constant, and sum rules", "Product and quotient rules", "Chain rule and composite functions", "Implicit and trigonometric differentiation", "Extrema and intervals of increase and decrease", "Applications to motion, optimisation, and curve sketching"])
    if any(k in t for k in ["integral", "تكامل", "area between", "مساحة", "volume", "حجوم"]):
        return (["المجموعات التقريبية والمساحة تحت المنحنى", "التكامل غير المحدد وقواعد التكامل الأساسية", "التكامل المحدد والنظرية الأساسية للتفاضل والتكامل", "التكامل بالتعويض", "المساحة بين منحنيين", "الحجوم بطريقة الأقراص والحلقات", "الحجوم بطريقة القشور الأسطوانية", "تطبيقات التكامل في الحركة وطول القوس"] if ar else
                ["Approximation sums and area under a curve", "Antiderivatives and basic integration rules", "Definite integrals and the Fundamental Theorem of Calculus", "Integration by substitution", "Area between curves", "Volumes by disks and washers", "Volumes by cylindrical shells", "Applications to motion and arc length"])
    if any(k in t for k in ["exponential", "logarith", "أسية", "لوغاريتم"]):
        return (["خصائص الدوال الأسية واللوغاريتمية", "التحويلات والتمثيل البياني", "قوانين اللوغاريتمات", "حل المعادلات الأسية", "حل المعادلات اللوغاريتمية", "النمو والاضمحلال", "النمذجة وتحليل المعلمات", "مراجعة وتطبيقات مترابطة"] if ar else
                ["Properties of exponential and logarithmic functions", "Transformations and graphing", "Laws of logarithms", "Solving exponential equations", "Solving logarithmic equations", "Growth and decay", "Modelling and parameter analysis", "Connected review and applications"])
    return []


def _generic_items(topic: str, language: str) -> list[str]:
    c = _core(topic, language)
    if normalize_language(language) == "Arabic":
        return [f"المفاهيم والمصطلحات الأساسية في {c}", f"التمثيلات والأمثلة الموجهة في {c}", f"تطبيق المهارات والاستراتيجيات في {c}", f"حل مشكلات متعددة الخطوات في {c}", f"تحليل الأخطاء وتبرير الحلول في {c}", f"تطبيقات واقعية ومهمة أداء في {c}"]
    return [f"Core concepts and vocabulary of {c}", f"Representations and guided examples in {c}", f"Applying skills and strategies in {c}", f"Multi-step problem solving in {c}", f"Error analysis and justification in {c}", f"Real-world application and performance task in {c}"]


def _roadmap(topics: list[str], subject: str, language: str, count: int) -> list[str]:
    source = _localize(topics, language) or _defaults({"subject": subject}, language)
    out: list[str] = []
    seen: set[str] = set()
    for topic in source:
        items = _math_items(topic, language) if _is_math(subject) else []
        for item in items or _generic_items(topic, language):
            key = re.sub(r"\W+", "", item.casefold())
            if key and key not in seen:
                seen.add(key); out.append(item)
            if len(out) >= count:
                return out
    while len(out) < count:
        for item in _generic_items(source[len(out) % len(source)], language):
            if item not in out:
                out.append(item)
            if len(out) >= count:
                break
    return out[:count]


def _objectives(topic: str, language: str) -> str:
    c = _core(topic, language)
    if normalize_language(language) == "Arabic":
        return f"• يفسر المفاهيم والعلاقات المرتبطة بـ {c} مستخدماً تمثيلاً مناسباً.\n• يطبق استراتيجية صحيحة لحل مسائل {c} ويبرر خطواته ويتحقق من معقولية الناتج."
    return f"• Explain the concepts and relationships in {c} using an appropriate representation.\n• Apply a valid strategy to solve {c} problems, justify the steps, and verify the result."


def _ai_literacy(index: int, language: str) -> str:
    ar = normalize_language(language) == "Arabic"
    ar_items = ["يقارن الطالب حله المستقل بمقترح رقمي ويتحقق من الدقة.", "يختبر الطالب جودة أمر رقمي ويحدد المعلومات الناقصة.", "يكتشف الطالب خطأً أو تحيزاً في مخرج رقمي ويصححه بالدليل.", "يوثق الطالب ما عدله بعد التغذية الراجعة الرقمية دون مشاركة بيانات شخصية."]
    en_items = ["Compare an independent solution with a digital suggestion and verify accuracy.", "Test prompt quality and identify missing information.", "Detect and correct an error or bias in a digital output using evidence.", "Document revisions after digital feedback without sharing personal data."]
    return (ar_items if ar else en_items)[index % 4]


def _resources(language: str) -> str:
    return ("الكتاب المدرسي، أمثلة مختارة، أوراق عمل متدرجة، السبورة التفاعلية، جيوجبرا أو ديسموس، وأداة ذكاء اصطناعي معتمدة." if normalize_language(language) == "Arabic" else "Textbook, selected examples, graduated worksheets, interactive board, GeoGebra or Desmos, and an approved AI tool.")


def generate_medium(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> MediumPlan:
    language = normalize_language(language); ar = language == "Arabic"
    subject = localize_subject(meta.get("subject", "Subject"), language); grade = localize_grade(meta.get("grade", ""), language)
    items = _roadmap(topics, subject, language, 20)
    weeks: list[MediumWeek] = []
    for idx in range(14):
        group = items[idx:idx + 2] if idx < 6 else items[min(len(items)-1, idx+1):min(len(items), idx+3)]
        if not group: group = [items[idx % len(items)]]
        weeks.append(MediumWeek(content="\n".join(f"• {x}" for x in group), learning_objectives=_objectives(group[0], language), ai_literacy=_ai_literacy(idx, language), resources=_resources(language)))
    localized = _localize(topics, language) or items[:8]
    if ar:
        return MediumPlan(title=f"الخطة متوسطة المدى - {subject} - {grade}", targets="تنظيم محتوى الفصل في تسلسل مترابط، رفع مستوى الإتقان، تنمية الاستدلال وحل المشكلات، وتطبيق الاستخدام المسؤول للأدوات الرقمية.", weeks=weeks, assessment_opportunities="تقويم تشخيصي، أسئلة صفية موجهة، مهام أداء، أوراق عمل متدرجة، اختبارات قصيرة، تحليل أخطاء، مراجعة تراكمية، وتقويم ختامي.", century_skills="التفكير الناقد، حل المشكلات، التواصل الرياضي، التعاون، الإبداع، الثقافة الرقمية، وإدارة التعلم.", vocabulary="، ".join(localized[:10]), eps_guiding_statement="تعلم عالي الجودة من خلال الاستقصاء والتفكير الناقد والتعاون والتغذية الراجعة والتطبيق الواقعي مع المسؤولية والاحترام.", global_citizenship="التنمية المستدامة، احترام التنوع، التواصل الفعال، واتخاذ قرارات مسؤولة قائمة على الأدلة.", cross_curricular="روابط هادفة مع العلوم والتقنية وتحليل البيانات والاستدامة وفق موضوعات المادة.", national_identity="المجال: الثقافة والقيم والمواطنة. الأبعاد المقترحة: الاحترام والانتماء والتراث والمحافظة على الموارد.", ai_integration_approach="استخدام موجه لأدوات معتمدة في التمثيل والتحقق والتغذية الراجعة دون استبدال تفكير الطالب.", guardrails_prompt_controls="تحديد المهمة والسياق، استخدام أدوات معتمدة، منع البيانات الشخصية، والتحقق من المخرجات قبل اعتمادها.", cognitive_integrity_strategy="ينجز الطالب محاولة مستقلة ويشرح تفكيره قبل الدعم الرقمي، ثم يقارن ويصحح ويوثق التعلم.", ai_safeguarding="حماية الخصوصية، فحص الدقة والتحيز، عدم رفع بيانات أو صور شخصية، والإفصاح عن المساعدة الرقمية عند الحاجة.", compliance=[ComplianceItem(area="تكامل المنهج", milestone="اختيار استخدام رقمي هادف مرتبط بهدف تعلم", responsible_person=meta.get("teacher", "المعلم"), target_date="طوال الفصل", status="قيد التنفيذ"), ComplianceItem(area="تدريب الطلبة", milestone="تدريب الطلبة على التحقق والاستخدام المسؤول", responsible_person=meta.get("teacher", "المعلم"), target_date="قبل الأسبوع الرابع", status="مخطط"), ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة المستقلة الأولى", responsible_person=meta.get("teacher", "المعلم"), target_date="كل مهمة", status="قيد التنفيذ"), ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة دون بيانات شخصية", responsible_person=meta.get("teacher", "المعلم"), target_date="طوال الفصل", status="قيد التنفيذ")])
    return MediumPlan(title=f"Medium Term Plan - {subject} - {grade}", targets="Sequence term content coherently, improve mastery, develop reasoning and problem solving, and apply responsible digital learning.", weeks=weeks, assessment_opportunities="Diagnostic checks, targeted questioning, performance tasks, graduated worksheets, quizzes, error analysis, cumulative review, and summative assessment.", century_skills="Critical thinking, problem solving, mathematical communication, collaboration, creativity, digital literacy, and self-management.", vocabulary=", ".join(localized[:10]), eps_guiding_statement="High-quality learning through inquiry, critical thinking, collaboration, feedback, real-world application, responsibility, and respect.", global_citizenship="Sustainable development, effective communication, valuing diversity, and evidence-based responsible decisions.", cross_curricular="Purposeful links to science, technology, data analysis, and sustainability according to the subject content.", national_identity="Domain: Culture, Values, Citizenship. Suggested dimensions: respect, belonging, heritage, and conservation.", ai_integration_approach="Teacher-guided use of approved tools for representation, verification, and feedback without replacing student thinking.", guardrails_prompt_controls="Define task and context, use approved tools, enter no personal data, and verify outputs before acceptance.", cognitive_integrity_strategy="Students complete and explain an independent first attempt before digital support, then compare, correct, and document learning.", ai_safeguarding="Protect privacy, check accuracy and bias, upload no personal data or images, and acknowledge digital assistance where appropriate.", compliance=[ComplianceItem(area="Curriculum Integration", milestone="Select purposeful digital use linked to a learning objective", responsible_person=meta.get("teacher", "Teacher"), target_date="Throughout Term", status="In Progress"), ComplianceItem(area="Student Training", milestone="Train students in verification and responsible use", responsible_person=meta.get("teacher", "Teacher"), target_date="By Week Four", status="Planned"), ComplianceItem(area="Cognitive Integrity", milestone="Record an independent first attempt", responsible_person=meta.get("teacher", "Teacher"), target_date="Every Task", status="In Progress"), ComplianceItem(area="Privacy and Safety", milestone="Use approved tools without personal data", responsible_person=meta.get("teacher", "Teacher"), target_date="Throughout Term", status="In Progress")])


def generate_long(meta: dict, source_text: str, topics: list[str], language: str, instructions: str = "") -> LongPlan:
    language = normalize_language(language); ar = language == "Arabic"
    subject = localize_subject(meta.get("subject", "Subject"), language)
    items = _roadmap(topics, subject, language, 18)
    assessments_ar = ["تقويم تشخيصي للمعرفة السابقة، اختبار مهارات قصير، ومهمة أداء فردية تتبعها تغذية راجعة نوعية.", "اختبار تحصيلي يتضمن أسئلة متعددة الخطوات، مهمة تطبيقية، ومراجعة تراكمية للمفاهيم الأساسية.", "اختبار قصير، تحليل أخطاء شائعة، ومهمة حل مشكلات تتطلب اختيار الاستراتيجية وتبريرها.", "تقويم تحصيلي، مشروع مصغر أو مهمة أداء مرتبطة بتطبيق واقعي، ومناقشة للأدلة والنتائج.", "مهمة تطبيقية، اختبار قصير، ومراجعة مترابطة تقيس الانتقال بين التمثيلات ودقة الاستدلال.", "تقويم ختامي شامل، مراجعة منظمة، تحليل بيانات الإتقان، وخطة دعم أو إثراء للفصل التالي."]
    assessments_en = ["Diagnostic assessment of prerequisite knowledge, a skills-based quiz, and an individual performance task with qualitative feedback.", "Achievement test with multi-step questions, an applied task, and cumulative review of core concepts.", "Quiz, analysis of common errors, and a problem-solving task requiring strategy selection and justification.", "Achievement assessment, a mini-project or real-world performance task, and evidence-based discussion of results.", "Applied task, quiz, and connected review measuring movement between representations and accuracy of reasoning.", "Comprehensive summative assessment, structured review, mastery-data analysis, and a support or enrichment plan for the next term."]
    titles_ar = ["الفترة الأولى - الفصل الدراسي الأول", "الفترة الثانية - الفصل الدراسي الأول", "الفترة الأولى - الفصل الدراسي الثاني", "الفترة الثانية - الفصل الدراسي الثاني", "الفترة الأولى - الفصل الدراسي الثالث", "الفترة الثانية - الفصل الدراسي الثالث"]
    titles_en = ["Autumn 1", "Autumn 2", "Spring 1", "Spring 2", "Summer 1", "Summer 2"]
    halves = []
    for idx in range(6):
        group = items[idx*3:idx*3+3]
        halves.append(HalfTerm(title=(titles_ar if ar else titles_en)[idx], content="\n".join(f"• {x}" for x in group), summative_assessment=(assessments_ar if ar else assessments_en)[idx]))
    teacher = meta.get("teacher", "المعلم" if ar else "Teacher")
    if ar:
        compliance = [ComplianceItem(area="تكامل المنهج", milestone="توظيف رقمي هادف مرتبط بأهداف المنهج", responsible_person=teacher, target_date="نهاية الفترة الثانية", status="مخطط"), ComplianceItem(area="تعرض الطلبة", milestone="تطبيق روتين آمن للتحقق والاستخدام المسؤول", responsible_person=teacher, target_date="نهاية الفترة الثالثة", status="مخطط"), ComplianceItem(area="النزاهة المعرفية", milestone="توثيق المحاولة المستقلة الأولى", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ"), ComplianceItem(area="الخصوصية والسلامة", milestone="استخدام أدوات معتمدة دون بيانات شخصية", responsible_person=teacher, target_date="طوال العام", status="قيد التنفيذ")]
    else:
        compliance = [ComplianceItem(area="Curriculum Integration", milestone="Purposeful digital use linked to curriculum goals", responsible_person=teacher, target_date="End of Period Two", status="Planned"), ComplianceItem(area="Student Exposure", milestone="Safe-use and verification routines established", responsible_person=teacher, target_date="End of Period Three", status="Planned"), ComplianceItem(area="Cognitive Integrity", milestone="Independent first attempts documented", responsible_person=teacher, target_date="Throughout Year", status="In Progress"), ComplianceItem(area="Privacy and Safety", milestone="Approved tools used without personal data", responsible_person=teacher, target_date="Throughout Year", status="In Progress")]
    return LongPlan(half_terms=halves, compliance=compliance)
