from __future__ import annotations
import json
import os
import re
import time
from typing import Dict

try:
    from openai import OpenAI
    from pydantic import BaseModel
except Exception:
    OpenAI = None
    BaseModel = object

RLM = "\u200f"
CACHE = {}
TTL = 1200


class Plan(BaseModel):
    keywords: str
    sdg: str
    strategies: str
    intervention: str
    learning_outcomes: str
    differentiation: str
    success_criteria: str
    starter: str
    main: str
    teacher_led: str
    student_led: str
    plenary: str
    kpi: str
    resources: str
    identity: str
    competency: str
    curriculum: str


def numbered(items, lang):
    prefix = RLM if lang == "ar" else ""
    return "\n".join(f"{prefix}{i}. {item}" for i, item in enumerate(items, 1))


def family(subject):
    value = (subject or "").lower()
    if any(x in value for x in ("لغة عربية", "عربي", "arabic")):
        return "ar"
    if any(x in value for x in ("رياض", "math", "calculus", "جبر", "هندسة")):
        return "math"
    if any(x in value for x in ("فيزياء", "physics", "كيمياء", "chemistry", "أحياء", "biology", "علوم", "science")):
        return "science"
    if any(x in value for x in ("انجليزي", "english")):
        return "english"
    return "general"


def special(lesson, app):
    lang = lesson.language
    topic = lesson.topic.strip()
    subject = lesson.subject.strip()
    cls = lesson.class_name.strip()
    t = topic.lower()
    sf = family(subject)

    if lang == "ar" and sf == "ar" and any(x in t for x in ("النعت", "نعت", "الصفة")):
        return dict(
            subject=subject,
            class_name=cls,
            keywords="النعت، المنعوت، المطابقة، الإعراب، التعريف والتنكير، النوع، العدد",
            sdg="SDG 4 التعليم الجيد: تنمية الكفاءة اللغوية والتواصل الدقيق والاعتزاز باللغة العربية.",
            strategies="تمهيد بجمل قصيرة، استقراء القاعدة، تفكير بصوت عالٍ، تدريب موجه، تطبيق فردي، تصحيح خطأ، وبطاقة خروج.",
            intervention="دعم: جدول مطابقة، مثال جزئي، تلوين النعت والمنعوت، وشريك داعم.\nخطأ متوقع: الخلط بين النعت والخبر.",
            learning_outcomes=numbered([
                "أعرّف النعت والمنعوت تعريفًا دقيقًا.",
                "أستخرج النعت والمنعوت من جمل متنوعة.",
                "أحدد أوجه المطابقة بينهما.",
                "أعرب النعت إعرابًا صحيحًا.",
                "أحوّل الجملة إلى المثنى والجمع مع ضبط المطابقة.",
                "أميز بين النعت والخبر وأبرر اختياري.",
            ], "ar"),
            differentiation=numbered([
                "دعم: كلمات ملوّنة وجدول مطابقة ومثال جزئي.",
                "المستوى المتوقع: استخراج النعت والمنعوت وإعرابهما.",
                "متقدمون: إنتاج جمل وتصحيح جملة خاطئة.",
                "IEP/APL: تقليل عدد الجمل وتقديم اختيارات بصرية.",
            ], "ar"),
            success_criteria=numbered([
                "أحدد النعت والمنعوت دون خلط.",
                "أذكر ثلاثة أوجه مطابقة.",
                "أعرب النعت بعلامة صحيحة.",
                "أحوّل مثالًا إلى المثنى أو الجمع.",
                "أفسر الفرق بين النعت والخبر.",
                "أحقق 80% فأكثر في بطاقة الخروج.",
            ], "ar"),
            starter="تمهيد: يعرض المعلم «الطالبُ مجتهدٌ» و«الطالبُ المجتهدُ حاضرٌ».\nسؤال تشخيصي: ما وظيفة كلمة «المجتهد» في كل جملة؟\nاستجابة متوقعة: خبر في الأولى ونعت في الثانية.",
            main=numbered([
                "مثال محلول: في «جاءَ الطالبُ المجتهدُ»، المجتهدُ نعت مرفوع؛ لأنه وصف الطالب وطابقه في الرفع والتعريف والتذكير والإفراد.",
                "تدريب موجه: استخرج النعت والمنعوت ووجه المطابقة في «كرّمت المدرسةُ الطالباتِ المتميزاتِ» و«شاهدتُ منظرًا جميلًا».",
                "تطبيق فردي: كوّن جملتين بنعت معرف ونعت نكرة ثم تبادل التصحيح.",
                "HOTS: لماذا تعد «مجتهدٌ» خبرًا في الجملة الأولى ونعتًا في الثانية؟",
            ], "ar"),
            teacher_led="دور المعلم: يستخرج القاعدة من الأمثلة، وينمذج الإعراب، ثم يستخدم أسئلة تحقق قصيرة: ما المنعوت؟ ماذا يصفه النعت؟ كيف طابقه؟",
            student_led="دور الطلاب: يحلون التدريب الموجه في أزواج، ثم ينتج كل طالب مثالًا جديدًا ويشرح المطابقة لزميله.",
            plenary="بطاقة خروج:\n1. استخرج النعت والمنعوت.\n2. حدّد وجهين للمطابقة.\n3. صحح خطأً نحويًا واحدًا.",
            kpi="AFL: أربع جمل تقيس الاستخراج والمطابقة والإعراب والتمييز بين النعت والخبر. معيار النجاح 80%.",
            resources="بطاقات جمل، جدول المطابقة، سبورة ذكية، أقلام تلوين، ورقة عمل، بطاقة خروج.",
            identity="الهوية الوطنية: جمل عن الاحترام والتميز والاعتزاز باللغة العربية في دولة الإمارات.",
            competency="التواصل اللغوي، التفكير الناقد، التعاون، الإبداع، التعلم الذاتي.",
            curriculum=f"المادة: {subject} | الصف: {cls} | الدرس: {topic}\nروابط قبلية: الاسم والإعراب.\nروابط لاحقة: التوابع.",
            _mode="expert_fallback",
        )

    if lang == "ar" and sf == "math" and (
        "limit" in t or "limits" in t or "نهاية" in t or "النهايات" in t
    ):
        return dict(
            subject=subject,
            class_name=cls,
            keywords="النهاية، التعويض المباشر، الصورة غير المعينة، التحليل، الاختصار، الاقتراب من اليمين واليسار",
            sdg="SDG 4 التعليم الجيد: تنمية التفكير التحليلي والدقة في اتخاذ القرار باستخدام التمثيلات الرياضية.",
            strategies="تمهيد تشخيصي، نموذج محلول، تدريب موجه، مناقشة خطأ شائع، تطبيق فردي، سؤال HOTS، وبطاقة خروج.",
            intervention="دعم: بطاقة خطوات، تلوين العامل المشترك، وجدول قيم.\nخطأ متوقع: التعويض بعد الاختصار دون توضيح شرط المجال.",
            learning_outcomes=numbered([
                "أفسر معنى نهاية الدالة عند نقطة.",
                "أتحقق من إمكانية استخدام التعويض المباشر.",
                "أتعرف الصورة غير المعينة من النوع صفر على صفر.",
                "أوجد نهاية كثيرة حدود بالتعويض المباشر.",
                "أوجد نهاية دالة كسرية باستخدام التحليل والاختصار.",
                "أبرر صحة الحل باستخدام التمثيل العددي أو البياني.",
            ], "ar"),
            differentiation=numbered([
                "دعم: جدول قيم وبطاقة خطوات ومثال جزئي.",
                "المستوى المتوقع: تطبيق التعويض المباشر والتحليل.",
                "متقدمون: مقارنة حل جبري بتمثيل بياني.",
                "IEP/APL: تقليل عدد الخطوات وتوفير نموذج بصري.",
            ], "ar"),
            success_criteria=numbered([
                "أحدد طريقة الحل المناسبة.",
                "أتعرف الصورة غير المعينة بدقة.",
                "أحلل البسط أو المقام دون خطأ.",
                "أختصر العامل المشترك مع توضيح الشرط.",
                "أكتب الناتج النهائي بصورة صحيحة.",
                "أحقق 80% فأكثر في بطاقة الخروج.",
            ], "ar"),
            starter=(
                "تمهيد: يعرض المعلم قيمة الدالة قرب العدد 2 ويطلب توقع القيمة التي تقترب منها.\n"
                "[[EQ:f(x)=x^2+1]]\n"
                "[[EQ:lim(x,2,f(x))]]\n"
                "سؤال تشخيصي: هل يكفي التعويض المباشر؟ ولماذا؟"
            ),
            main=numbered([
                "مثال محلول: نهاية كثيرة حدود بالتعويض المباشر.\n[[EQ:lim(x,3,2x^2-x+4)]]\n[[EQ:2(3)^2-3+4=19]]",
                "تدريب موجه: نهاية كسرية تظهر الصورة صفر على صفر؛ يحلل الطلاب البسط ثم يختصرون العامل المشترك.\n[[EQ:lim(x,2,frac(x^2-4,x-2))]]\n[[EQ:x^2-4=(x-2)(x+2)]]\n[[EQ:lim(x,2,x+2)=4]]",
                "تطبيق فردي: اختر الطريقة المناسبة ثم بررها في مسألة جديدة تجمع بين التعويض المباشر والتحليل.",
                "HOTS: كيف تتغير طريقة الحل إذا اختلفت النهاية اليمنى عن النهاية اليسرى؟",
            ], "ar"),
            teacher_led="دور المعلم: ينمذج قرار اختيار الاستراتيجية، ويشرح لماذا تظهر الصورة صفر على صفر، ثم يستخدم أسئلة تحقق بعد كل خطوة ويعالج خطأ الاختصار غير المبرر.",
            student_led="دور الطلاب: يكملون جدول قيم، ويحللون تعبيرًا جبريًا في أزواج، ثم يشرح كل طالب سبب اختيار طريقة الحل ويقارنها بتمثيل بياني.",
            plenary="بطاقة خروج:\n1. احسب نهاية بالتعويض المباشر.\n2. حل نهاية كسرية بالتحليل.\n3. اكتب سبب اختيارك للطريقة.",
            kpi="AFL: ثلاث مسائل قصيرة تقيس اختيار الاستراتيجية، صحة التحليل، ودقة التبرير. معيار النجاح 80%.",
            resources="سبورة ذكية، Desmos أو GeoGebra، جدول قيم، بطاقات خطوات، ورقة عمل، بطاقة خروج.",
            identity="ربط الدقة في تقدير القيم واتخاذ القرار بالتخطيط المسؤول والمشروعات المستدامة في دولة الإمارات.",
            competency="التفكير الناقد، حل المشكلات، التواصل الرياضي، التعاون، الكفاءة الرقمية.",
            curriculum=f"المادة: {subject} | الصف: {cls} | الدرس: {topic}\nروابط قبلية: التحليل والتعويض.\nروابط لاحقة: الاتصال والمشتقة.",
            _mode="expert_fallback",
        )

    if lang == "ar" and sf == "math" and "طول المنحنى" in t and any(x in t for x in ("مماس", "المماسات")):
        return dict(
            subject=subject,
            class_name=cls,
            keywords="المماس، ميل المماس، المشتقة، معدل التغير اللحظي، طول المنحنى، التكامل المحدد",
            sdg="SDG 4 + SDG 11: توظيف النمذجة الرياضية في التخطيط المستدام.",
            strategies="تمهيد تشخيصي، نموذج محلول، تدريب موجه، تطبيق فردي، مقارنة تمثيلات، وسؤال HOTS.",
            intervention="دعم: بطاقة خطوات ورسم مماس ومثال جزئي.\nخطأ متوقع: استخدام f(a) بدل f′(a) للميل.",
            learning_outcomes=numbered([
                "أفسر المشتقة عند نقطة بوصفها ميل المماس.",
                "أحسب نقطة التماس وميل المماس.",
                "أكتب معادلة المماس بصيغة النقطة والميل.",
                "أفسر طول المنحنى بوصفه تراكمًا للمسافة.",
                "أستخدم صيغة طول المنحنى في مثال.",
                "أقارن بين المسافة المستقيمة وطول المنحنى.",
            ], "ar"),
            differentiation=numbered([
                "دعم: رسم بياني وبطاقة خطوات.",
                "المستوى المتوقع: مثال مباشر للمماس.",
                "متقدمون: تفسير أثر المشتقة في طول المنحنى.",
                "IEP/APL: تقليل التعقيد وتوفير آلة حاسبة.",
            ], "ar"),
            success_criteria=numbered([
                "أميز بين f(a) و f′(a).",
                "أحسب ميل المماس.",
                "أكتب معادلة المماس.",
                "أفسر صيغة طول المنحنى.",
                "أطبق الصيغة في مثال موجه.",
                "أحقق 80% في بطاقة الخروج.",
            ], "ar"),
            starter="تمهيد: يقارن الطلاب بين خط قاطع وخط مماس ويربطون الميل بمعدل التغير.\n[[EQ:f(x)=x^2-3x]]\n[[EQ:x=1]]",
            main=numbered([
                "مثال محلول: أوجد نقطة التماس والميل ثم معادلة المماس.\n[[EQ:f(x)=x^2+1]]\n[[EQ:x=2]]\n[[EQ:m=f'(2)=4]]\n[[EQ:y-5=4(x-2)]]",
                "تدريب موجه: أوجد ميل المماس ومعادلته ثم فسّر الخطوات.\n[[EQ:f(x)=x^2-3x]]\n[[EQ:x=1]]",
                "تطبيق فردي: ناقش دور المشتقة في صيغة طول المنحنى.\n[[EQ:L=int(a,b,sqrt(1+(f'(x))^2),dx)]]",
                "HOTS: قارن بين الميل اللحظي وطول المنحنى التراكمي.",
            ], "ar"),
            teacher_led="دور المعلم: ينمذج نقطة التماس والمشتقة ومعادلة المماس، ثم يشرح عناصر صيغة طول المنحنى بالرسم.",
            student_led="دور الطلاب: يحلون تدريبًا موجهًا ثم تطبيقًا فرديًا ويشرحون الخطوات لزملائهم.",
            plenary="بطاقة خروج:\n1. احسب ميل مماس.\n2. اكتب معادلته.\n3. فسّر الجذر في صيغة طول المنحنى.",
            kpi="AFL: قيمة الدالة والمشتقة، معادلة المماس، تفسير الصيغة، وتصحيح خطأ. معيار النجاح 80%.",
            resources="سبورة ذكية، Desmos أو GeoGebra، آلة حاسبة، بطاقة خطوات، ورقة عمل.",
            identity="ربط طول المسار بتصميم طرق ومسارات أكثر كفاءة في دولة الإمارات.",
            competency="التفكير الناقد، حل المشكلات، التواصل الرياضي، التعاون، الكفاءة الرقمية.",
            curriculum=f"المادة: {subject} | الصف: {cls} | الدرس: {topic}",
            _mode="expert_fallback",
        )

    base = app.offline_content(lesson)
    base["_mode"] = "subject_specific_fallback"
    return base


def system_prompt(lang):
    ar = (
        "أنت خبير مناهج وتحضير دروس في مدارس الإمارات. أنشئ خطة حقيقية خاصة بالمادة والصف وعنوان الدرس، ولا تستخدم عبارات عامة. "
        "اكتب بلغة تربوية مهنية مختصرة ومناسبة لخلايا قالب Word الرسمي. "
        "نواتج التعلم ومعايير النجاح: 6 أسطر مرقمة بالأرقام الإنجليزية. التمايز: 4 أسطر. "
        "التمهيد يجب أن يحتوي: تمهيد، سؤال تشخيصي، واستجابة متوقعة، كل عنصر في سطر مستقل. "
        "الأنشطة الرئيسية يجب أن تكون 4 مجموعات مستقلة: مثال محلول، تدريب موجه، تطبيق فردي، وسؤال HOTS. "
        "دور المعلم يتضمن النمذجة وأسئلة التحقق وعلاج الخطأ المتوقع. دور الطلاب يتضمن نشاطًا واضحًا ودليل تعلم قابلًا للملاحظة. "
        "الخاتمة يجب أن تكون بطاقة خروج من 3 بنود. "
        "في اللغة العربية قدم أمثلة وإعرابًا؛ في الرياضيات قدم مثالًا محلولًا وتدريبًا موجهًا بمعادلات حقيقية؛ في العلوم قدم ملاحظة أو تجربة. "
        "ضع كل معادلة رياضية في سطر مستقل بين [[EQ:...]]. استخدم x^2 أو sqrt(...) أو frac(a,b) أو int(a,b,expression,dx) أو lim(x,a,expression). "
        "لا تستخدم LaTeX أو رمز الدولار، ولا تكتب أكثر من فكرة رئيسية في السطر الواحد، ولا تكرر المثال نفسه."
    )
    en = (
        "You are an expert UAE-school lesson planner. Produce a genuinely subject-specific, concise, professional plan for an official Word template. "
        "Learning outcomes and success criteria: 6 numbered lines. Differentiation: 4 numbered lines. "
        "Starter: hook, diagnostic question, expected response on separate lines. "
        "Main activities: exactly four clearly separated groups—worked example, guided practice, independent application, HOTS. "
        "Teacher-led must include modeling, checks for understanding, and misconception treatment. Student-led must include an observable learning product. "
        "Plenary must be a three-item exit ticket. For equations use separate [[EQ:...]] lines with x^2, sqrt(...), frac(a,b), int(a,b,expression,dx), or lim(x,a,expression). "
        "Do not use LaTeX or dollar signs. Avoid generic filler and repeated examples."
    )
    return ar if lang == "ar" else en


def clean_list(text, count, fallback, lang):
    parts = [
        re.sub(r"^\s*[\u200e\u200f]*(?:\d+|[٠-٩]+)[\.)-]?\s*", "", x).strip()
        for x in str(text or "").replace("\r", "").split("\n")
        if x.strip()
    ]
    fb = [
        re.sub(r"^\s*[\u200e\u200f]*\d+[\.)]\s*", "", x).strip()
        for x in fallback.split("\n")
        if x.strip()
    ]
    for item in fb:
        if len(parts) >= count:
            break
        parts.append(item)
    return numbered(parts[:count], lang)


def clean_main(text, fallback, lang):
    def groups_from(value):
        groups = []
        current = []
        for raw in str(value or "").replace("\r", "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            match = re.match(r"^\s*[\u200e\u200f]*(\d+)[\.)-]?\s*(.*)$", line)
            if match:
                if current:
                    groups.append("\n".join(current))
                current = [match.group(2).strip()]
            elif line.startswith("[[EQ:") and current:
                current.append(line)
            elif current:
                current.append(line)
            else:
                current = [line]
        if current:
            groups.append("\n".join(current))
        return groups

    groups = groups_from(text)
    fallback_groups = groups_from(fallback)
    for item in fallback_groups:
        if len(groups) >= 4:
            break
        groups.append(item)
    prefix = RLM if lang == "ar" else ""
    return "\n".join(f"{prefix}{i}. {group}" for i, group in enumerate(groups[:4], 1))


def build_expert_content(lesson, app):
    key = json.dumps(
        [
            lesson.subject,
            lesson.class_name,
            lesson.language,
            lesson.topic,
            lesson.notes,
            app.clean_text(lesson.source_text, 1800),
        ],
        ensure_ascii=False,
    )
    now = time.time()
    cached = CACHE.get(key)
    if cached and now - cached[0] < TTL:
        return dict(cached[1])

    fallback = special(lesson, app)
    if not os.getenv("OPENAI_API_KEY") or OpenAI is None or BaseModel is object:
        CACHE[key] = (now, fallback)
        return dict(fallback)

    try:
        client = OpenAI(timeout=55.0, max_retries=1)
        user = json.dumps(
            {
                "language": lesson.language,
                "subject": lesson.subject,
                "class": lesson.class_name,
                "lesson_title": lesson.topic,
                "periods": lesson.periods,
                "teacher_notes": lesson.notes,
                "uploaded_text": app.clean_text(lesson.source_text, 2200),
                "quality": "Use actual examples, a genuine worked model, guided practice, independent application, and an observable exit ticket.",
            },
            ensure_ascii=False,
        )
        response = client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            input=[
                {"role": "system", "content": system_prompt(lesson.language)},
                {"role": "user", "content": user},
            ],
            text_format=Plan,
            max_output_tokens=3800,
            store=False,
        )
        data = response.output_parsed.model_dump()
        out = {
            "subject": lesson.subject or fallback["subject"],
            "class_name": lesson.class_name or fallback["class_name"],
        }
        for key_name in Plan.model_fields:
            out[key_name] = app.clean_text(data.get(key_name) or fallback.get(key_name, ""))
        out["learning_outcomes"] = clean_list(
            out["learning_outcomes"], 6, fallback["learning_outcomes"], lesson.language
        )
        out["success_criteria"] = clean_list(
            out["success_criteria"], 6, fallback["success_criteria"], lesson.language
        )
        out["differentiation"] = clean_list(
            out["differentiation"], 4, fallback["differentiation"], lesson.language
        )
        out["main"] = clean_main(out["main"], fallback["main"], lesson.language)
        out["_mode"] = "ai_expert_v3"
        CACHE[key] = (now, out)
        return dict(out)
    except Exception:
        app.logger.exception("Expert AI failed; using subject fallback")
        fallback["_mode"] = "expert_fallback_after_ai_error"
        CACHE[key] = (now, fallback)
        return dict(fallback)
