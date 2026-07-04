from dataclasses import asdict
from datetime import datetime
import io
import re
import zipfile

from werkzeug.exceptions import HTTPException
from flask import redirect, url_for, Response, request, jsonify, send_file
from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH

import app as app_module

app = app_module.app
status_payload = app_module.status_payload
parse_lessons_from_request = app_module.parse_lessons_from_request
logger = app_module.logger
check_usage_limit = app_module.check_usage_limit
store_docx_file = app_module.store_docx_file
clean_text = app_module.clean_text
topic_family = app_module.topic_family
source_keywords = app_module.source_keywords

RLM = "\u200f"
LRM = "\u200e"


@app.route('/favicon.ico')
def favicon():
    return Response(status=204)


@app.route('/generate', methods=['GET'], endpoint='generate_get')
def generate_get():
    return redirect(url_for('index'))


def _ascii_name(prefix='Lesson_Plan', ext='docx'):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


def bullets(items, lang='ar'):
    """English digits in both languages. In Arabic, RLM keeps 1., 2. at the right edge."""
    if lang == 'ar':
        return '\n'.join(f"{RLM}{i}. {item}" for i, item in enumerate(items, 1))
    return '\n'.join(f"{i}. {item}" for i, item in enumerate(items, 1))


def detect_special_topic(topic: str, fam: str) -> str:
    t = (topic or '').lower()
    if any(x in t for x in ['طول المنحنى', 'arc length', 'curve length']) and any(x in t for x in ['مماس', 'مماسات', 'tangent']):
        return 'tangent_arc'
    if any(x in t for x in ['طول المنحنى', 'arc length', 'curve length']):
        return 'arc_length'
    if any(x in t for x in ['مماس', 'مماسات', 'tangent']):
        return 'tangent'
    if any(x in t for x in ['اشتقاق', 'مشتقة', 'derivative', 'differentiation']):
        return 'derivatives'
    if any(x in t for x in ['نهاية', 'نهايات', 'limit', 'continuity', 'اتصال']):
        return 'limits'
    if any(x in t for x in ['تكامل', 'integral', 'area under']):
        return 'integrals'
    if any(x in t for x in ['لوغاريتم', 'لوغاريتمات', 'log', 'exponential', 'أسية', 'أسي']):
        return 'logs'
    if any(x in t for x in ['مثلث', 'جا', 'جتا', 'ظا', 'trig', 'sin', 'cos', 'tan', 'radian']):
        return 'trig'
    if any(x in t for x in ['دالة', 'دوال', 'function', 'domain', 'range', 'تقارب', 'asymptote']):
        return 'functions'
    return fam


def math(s: str) -> str:
    """LaTeX-style text that remains readable inside Word table cells."""
    return f"{LRM}\\({s}\\){LRM}"


def lesson_examples(topic: str, subject: str, lang: str, fam: str):
    special = detect_special_topic(topic, fam)
    math_subject = any(w in (subject or '').lower() for w in ['math', 'رياض', 'calculus', 'حساب'])

    if lang == 'ar':
        if special == 'tangent_arc':
            return {
                'keywords': 'المماس، ميل المماس، المشتقة، طول المنحنى، معدل التغير اللحظي، التكامل المحدد',
                'concept': f'يربط الدرس بين المشتقة كمعدل تغير لحظي وبين طول المنحنى كتراكم للمسافة على فترة. الصيغ الأساسية: {math("m=f'(a)")}، {math("y-f(a)=f'(a)(x-a)")}، {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
                'worked': f'مثال محلول خاص بالدرس: إذا كانت {math("f(x)=x^2+1")} عند {math("x=2")} فإن {math("f(2)=5")} و {math("f'(x)=2x")} لذا {math("m=f'(2)=4")} ومعادلة المماس {math("y-5=4(x-2)")}. ثم نوضح أن طول المنحنى لا يساوي المسافة المستقيمة بين الطرفين بل يحسب بصيغة {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
                'guided': f'تدريب موجه: للدالة {math("f(x)=x^2-3x")} عند {math("x=1")} أوجد {math("f'(1)")}، واكتب معادلة المماس، ثم اشرح شفهيًا لماذا تدخل {math("f'(x)")} في صيغة طول المنحنى.',
                'hots': f'سؤال إثرائي: قارن بين ميل المماس عند نقطة واحدة وطول المنحنى على الفترة {math("[a,b]")}. أيهما يمثل قيمة لحظية وأيهما يمثل تراكمًا؟ ادعم إجابتك برسم صغير.',
                'misconception': 'الخلط بين \(f(a)\) و \(f′(a)\)، أو اعتبار طول المنحنى مساويًا للمسافة المستقيمة بين نقطتي البداية والنهاية.'
            }
        if special == 'tangent':
            return {
                'keywords': 'المماس، المشتقة، ميل المماس، معدل التغير اللحظي، معادلة الخط',
                'concept': f'يركز الدرس على تفسير {math("f'(a)")} كميل للمماس عند {math("x=a")} ثم استخدام معادلة الخط {math("y-y_1=m(x-x_1)")}.',
                'worked': f'مثال محلول: إذا كانت {math("f(x)=x^2+1")} و {math("a=2")}، فإن {math("f(2)=5")} و {math("f'(2)=4")}، إذن معادلة المماس {math("y-5=4(x-2)")}.',
                'guided': f'تدريب موجه: أوجد معادلة المماس للدالة {math("f(x)=x^2-3x")} عند {math("x=1")} مع توضيح الفرق بين قيمة الدالة وقيمة المشتقة.',
                'hots': 'سؤال إثرائي: إذا كان المماس أفقيًا عند نقطة، ماذا تستنتج عن قيمة المشتقة وسلوك الرسم قرب هذه النقطة؟',
                'misconception': 'استخدام قيمة الدالة بدل قيمة المشتقة عند حساب ميل المماس.'
            }
        if special == 'arc_length':
            return {
                'keywords': 'طول المنحنى، التكامل المحدد، المشتقة، التقدير العددي، المسافة التراكمية',
                'concept': f'يركز الدرس على بناء معنى طول المنحنى من مجموع قطع صغيرة ثم الوصول إلى الصيغة {math("L=\\int_a^b\\sqrt{1+(y')^2}\\,dx")}.',
                'worked': f'مثال محلول: من جدول قيم، نقسم الفترة إلى قطع ونحسب تقريبًا {math("L\\approx\\sum\\sqrt{(\\Delta x)^2+(\\Delta y)^2}")}، ثم نربط ذلك بالتكامل عندما تصبح القطع صغيرة جدًا.',
                'guided': 'تدريب موجه: قدّر طول منحنى من ثلاث قطع مستقيمة ثم قارن الناتج بالمسافة المستقيمة بين أول وآخر نقطة.',
                'hots': 'سؤال إثرائي: متى يمكن أن يقترب طول المنحنى من المسافة المستقيمة؟ ومتى يصبح الفرق كبيرًا؟',
                'misconception': 'اعتبار طول المنحنى مساويًا للمسافة الأفقية أو المسافة المستقيمة بين الطرفين.'
            }
        if special == 'limits':
            return {'keywords': 'النهاية، الاقتراب، الاتصال، عدم التعيين، التحليل الجبري', 'concept': f'يدرس الطلاب معنى {math("\\lim_{x\\to a} f(x)")} بالتمثيل العددي والبياني والجبري.', 'worked': f'مثال محلول: عالج عدم التعيين {math("0/0")} بالتحليل ثم احسب النهاية بعد الاختصار.', 'guided': 'تدريب موجه: اقرأ النهاية من جدول ثم تحقق من الرسم وحدد هل الدالة متصلة عند النقطة.', 'hots': 'سؤال إثرائي: هل يمكن أن توجد النهاية رغم أن قيمة الدالة غير معرفة؟ برر برسم أو مثال.', 'misconception': 'الاعتقاد أن النهاية تساوي دائمًا قيمة الدالة عند النقطة.'}
        if special == 'integrals':
            return {'keywords': 'التكامل، المساحة الموقعة، التراكم، الدالة الأصلية، النظرية الأساسية', 'concept': f'يربط الطلاب بين {math("\\int_a^b f(x)\\,dx")} والمساحة الموقعة والتراكم.', 'worked': f'مثال محلول: احسب {math("\\int_0^2 (x+1)\\,dx")} وفسر الناتج كمساحة تراكمية.', 'guided': 'تدريب موجه: قارن بين المساحة الهندسية والتكامل الموقّع عندما يقع جزء من الرسم أسفل محور x.', 'hots': 'سؤال إثرائي: متى يكون التكامل موجبًا رغم وجود جزء من الرسم أسفل المحور؟', 'misconception': 'الخلط بين المساحة الهندسية والتكامل المحدد ذي الإشارة.'}
        if special == 'functions':
            return {'keywords': 'الدالة، المجال، المدى، التحويلات، التمثيل البياني، التركيب', 'concept': 'يحلل الطلاب خصائص الدوال من التمثيل الجبري والبياني ويصفون أثر التحويلات.', 'worked': 'مثال محلول: حدد المجال والمدى من رسم دالة ثم صف انتقالًا رأسيًا أو أفقيًا.', 'guided': 'تدريب موجه: مثل دالة بسيطة وحدد المجال والمدى ونقطة تقاطع أو خاصية رئيسة.', 'hots': 'سؤال إثرائي: كيف يتغير المجال والمدى بعد تركيب دالتين أو أخذ الدالة العكسية؟', 'misconception': 'الخلط بين المجال والمدى أو ترتيب التحويلات.'}
        if math_subject:
            return {'keywords': f'{topic}، مفاهيم رياضية، تبرير، تمثيل، حل مشكلات', 'concept': f'يركز الدرس على بناء فهم رياضي دقيق لموضوع {topic} من خلال مثال محلول وتدريب موجه وتفسير للناتج.', 'worked': f'مثال محلول خاص بدرس {topic}: يعرض المعلم مسألة مباشرة، يحدد المعطيات، يختار القاعدة المناسبة، ثم يكتب خطوات الحل بلغة رياضية منظمة.', 'guided': f'تدريب موجه: يحل الطلاب مسألة مشابهة في {topic} مع سؤال تفسير يوضح معنى الناتج.', 'hots': f'سؤال إثرائي: عدّل شرطًا واحدًا في المسألة، ثم ناقش كيف يؤثر ذلك في طريقة الحل أو الناتج.', 'misconception': 'خطأ شائع مرتبط باختيار القاعدة أو تفسير الناتج.'}
        return {'keywords': f'{topic}، مفاهيم أساسية، تطبيق، تقويم', 'concept': f'درس متخصص في {subject}: يربط الطلاب بين المفهوم والتطبيق من خلال نشاط موجه وسؤال تحقق.', 'worked': f'مثال محلول مرتبط مباشرة بموضوع {topic} في مادة {subject}.', 'guided': f'تدريب موجه على {topic} مع تغذية راجعة فورية.', 'hots': f'سؤال تفكير عليا: طبق فكرة {topic} في موقف جديد.', 'misconception': 'خطأ شائع يتم تحديده من إجابات الطلاب.'}

    # English
    if special == 'tangent_arc':
        return {
            'keywords': 'tangent line, derivative, tangent slope, arc length, instantaneous rate of change, definite integral',
            'concept': f'The lesson links derivative as instantaneous slope with arc length as accumulated distance. Key formulae: {math("m=f'(a)")}, {math("y-f(a)=f'(a)(x-a)")}, {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
            'worked': f'Worked example: For {math("f(x)=x^2+1")} at {math("x=2")}, {math("f(2)=5")} and {math("f'(x)=2x")}, so {math("m=f'(2)=4")} and the tangent line is {math("y-5=4(x-2)")}. Then connect curve length to {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
            'guided': f'Guided practice: For {math("f(x)=x^2-3x")} at {math("x=1")}, find {math("f'(1)")}, write the tangent equation, and explain why {math("f'(x)")} appears in the arc-length formula.',
            'hots': f'HOTS: Compare tangent slope at one point with arc length on {math("[a,b]")}. Which is instantaneous and which is accumulated? Justify with a sketch.',
            'misconception': 'Confusing \(f(a)\) with \(f′(a)\), or treating curve length as straight-line distance between endpoints.'
        }
    return {'keywords': f'{topic}, key concepts, application, reasoning', 'concept': f'Students build subject-specific understanding of {topic} in {subject} through a worked example, guided practice, and interpretation.', 'worked': f'Worked example directly linked to {topic}, with clear steps, key vocabulary, and reasoning.', 'guided': f'Guided practice on {topic} followed by an interpretation question.', 'hots': f'HOTS: modify one condition in the problem and explain how the strategy or result changes.', 'misconception': 'A common misconception linked to method selection or interpretation.'}


def stable_content(lesson):
    lang = lesson.language
    fam = topic_family(lesson.topic, lesson.source_text)
    topic = (lesson.topic or ('الدرس' if lang == 'ar' else 'the lesson')).strip()
    subject = (lesson.subject or ('رياضيات' if lang == 'ar' else 'Mathematics')).strip()
    class_name = (lesson.class_name or ('الثاني عشر متقدم' if lang == 'ar' else 'Grade 12 Advanced')).strip()
    ex = lesson_examples(topic, subject, lang, fam)
    extra_kw = source_keywords(lesson.source_text, lang)
    keywords = ex['keywords'] + (('، ' + extra_kw) if lang == 'ar' and extra_kw else (', ' + extra_kw) if extra_kw else '')
    note = lesson.notes.strip()
    if lang == 'ar':
        return {
            'subject': subject,
            'class_name': class_name,
            'keywords': keywords,
            'sdg': 'SDG 4 التعليم الجيد + SDG 11 مدن ومجتمعات مستدامة: توظيف المعرفة في قراءة النماذج الكمية واتخاذ قرارات دقيقة ومسؤولة.',
            'strategies': 'استراتيجية مخصصة للدرس: تمهيد تشخيصي، نموذج محلول، تفكير بصوت عالٍ، تدريب موجه، تطبيق مستقل قصير، سؤال HOTS، وتغذية راجعة فورية.' + (f'\nملاحظة المعلم: {note}' if note else ''),
            'intervention': 'خطة دعم: بطاقة خطوات، مثال جزئي، أسئلة تحقق قصيرة، وشريك داعم. إذا أخفق أكثر من 25% في AFL يتم تنفيذ إعادة تدريس قصيرة.\nخطأ متوقع: ' + ex['misconception'],
            'learning_outcomes': bullets([
                f'أفسر المفهوم الرئيس في درس {topic} باستخدام لغة ورموز دقيقة.',
                f'أوظف الصيغة أو القاعدة المناسبة في سياق {subject}.',
                'أحل مثالًا مباشرًا بخطوات منظمة وأبرر سبب كل خطوة.',
                'أطبق الفكرة في مسألة متدرجة مرتبطة بعنوان الدرس.',
                'أفسر الناتج رياضيًا/بيانيًا وأتحقق من معقوليته.',
                'أصحح خطأً شائعًا مرتبطًا بالدرس وأوضح سبب التصحيح.'
            ], 'ar'),
            'differentiation': bullets([
                'دعم: خطوات مرقمة + مثال جزئي + تقليل الحمل الحسابي عند الحاجة.',
                'مستوى متوقع: تدريب موجه ثم سؤال مستقل مشابه للنموذج.',
                'متقدمون: سؤال HOTS يتطلب تفسيرًا أو مقارنة أو تعميمًا.',
                'IEP/APL: تبسيط الصياغة، وقت إضافي، وتمثيل بصري عند الحاجة.'
            ], 'ar'),
            'success_criteria': bullets([
                f'أستطيع شرح فكرة {topic} بدقة.',
                'أستطيع اختيار القاعدة أو النموذج المناسب.',
                'أستطيع كتابة خطوات حل واضحة ومنظمة.',
                'أستطيع استخدام لغة رياضية ورموز صحيحة.',
                'أستطيع تفسير الناتج وتصحيح خطأ شائع.',
                'أحقق 80% فأكثر في Exit Ticket أو أحدد خطوة تحسين.'
            ], 'ar'),
            'starter': f'نشاط تمهيدي (5-7 دقائق): سؤال تشخيصي مرتبط بعنوان الدرس، ثم مقارنة إجابتين لتحديد الفكرة الصحيحة والخطأ المتوقع.\n{ex["guided"]}',
            'main': 'أنشطة رئيسية منظمة:\n' + bullets([ex['worked'], ex['guided'], 'تطبيق فردي قصير ثم مقارنة زوجية للحل والخطوات.', ex['hots']], 'ar'),
            'teacher_led': f'دور المعلم: يشرح النموذج المحلول، يبرز الرموز والصيغ، ويوجه أسئلة تحقق قصيرة بعد كل خطوة.\n{ex["concept"]}',
            'student_led': 'دور الطلاب: يحلون تدريبًا موجهًا ثم سؤالًا مستقلًا، يشرح كل طالب خطوة لزميله، ويكتب جملة تفسيرية توضح معنى الناتج.',
            'plenary': 'خاتمة وتقويم: Exit Ticket من 3 أجزاء: مهارة مباشرة، تفسير رياضي، وتصحيح خطأ شائع. يعرض المعلم إجابة نموذجية وخطوة تحسين.',
            'kpi': 'KPI AFL Task: 4 أسئلة قصيرة: مفهوم، تطبيق مباشر، تفسير، وتصحيح خطأ. معيار النجاح 80% فأكثر مع تدخل فوري لمن هم دون ذلك.',
            'resources': 'السبورة الذكية، ورقة عمل قصيرة، آلة حاسبة عند الحاجة، بطاقات خطوات، رسم بياني/جدول قيم، Classroom Monitor، دفتر الطالب.',
            'identity': 'الهوية الوطنية والاستدامة: ربط الدقة والانضباط الرياضي بثقافة التميز في دولة الإمارات واستخدام مثال كمي يخدم التفكير المستدام.',
            'competency': 'كفاءات: تفكير ناقد، حل مشكلات، تواصل رياضي، تعاون، إبداع، مسؤولية ذاتية، ووعي رقمي.',
            'curriculum': f'ارتباط المنهج: {subject} - {class_name} - {topic}. يتكامل مع التحليل، التمثيل، التفسير، واستخدام النماذج في مواقف حقيقية.',
            '_mode': 'stable_professional_ar_ltr_digits'
        }
    return {
        'subject': subject,
        'class_name': class_name,
        'keywords': keywords,
        'sdg': 'SDG 4 Quality Education + SDG 11 Sustainable Cities: applying knowledge to interpret quantitative models and make responsible decisions.',
        'strategies': 'Lesson-specific strategy: diagnostic starter, worked example, think-aloud modelling, guided practice, short independent application, HOTS question, and immediate feedback.' + (f'\nTeacher note: {note}' if note else ''),
        'intervention': 'Support plan: step card, partial worked example, short check questions, and supportive peer. If more than 25% miss the AFL task, reteach briefly.\nLikely misconception: ' + ex['misconception'],
        'learning_outcomes': bullets([f'Explain the key concept in {topic} using accurate language and notation.', f'Use the appropriate formula, model, or rule in {subject}.', 'Solve a direct example with organised steps and justification.', 'Apply the idea to a progressive problem linked to the lesson title.', 'Interpret the result mathematically/graphically and check reasonableness.', 'Correct a lesson-specific misconception and justify the correction.'], 'en'),
        'differentiation': bullets(['Support: numbered steps, partial example, and reduced calculation load when needed.', 'Expected level: guided practice followed by a similar independent question.', 'Advanced learners: HOTS task requiring interpretation, comparison, or generalisation.', 'IEP/APL: simplified wording, additional time, and visual representation where appropriate.'], 'en'),
        'success_criteria': bullets([f'I can explain the idea of {topic} accurately.', 'I can select the correct rule or model.', 'I can write clear and organised solution steps.', 'I can use correct mathematical language and notation.', 'I can interpret the result and correct a common error.', 'I can score at least 80% in the Exit Ticket or identify an improvement step.'], 'en'),
        'starter': f'Starter (5-7 min): diagnostic question linked to the lesson title, then compare two answers to identify correct reasoning and the likely error.\n{ex["guided"]}',
        'main': 'Organised main activities:\n' + bullets([ex['worked'], ex['guided'], 'Short independent application followed by paired comparison of solution steps.', ex['hots']], 'en'),
        'teacher_led': f'Teacher role: model the worked example, highlight notation and formulae, and ask short check questions after each step.\n{ex["concept"]}',
        'student_led': 'Student role: complete guided practice, solve one independent question, explain one step to a peer, and write a short interpretation sentence.',
        'plenary': 'Plenary: 3-part Exit Ticket: direct skill, mathematical interpretation, and common-error correction. Teacher shares a model answer and improvement step.',
        'kpi': 'KPI AFL Task: 4 short questions: concept, direct application, interpretation, and error correction. Success benchmark: 80% or higher with immediate intervention below benchmark.',
        'resources': 'Smart board, short worksheet, calculator where needed, step cards, graph/value table, Classroom Monitor, student notebook.',
        'identity': 'UAE identity and sustainability: connect precision and mathematical discipline to the UAE culture of excellence and sustainable thinking.',
        'competency': 'Competencies: critical thinking, problem solving, mathematical communication, collaboration, creativity, self-management, and digital awareness.',
        'curriculum': f'Curriculum link: {subject} - {class_name} - {topic}. Integrated with analysis, representation, interpretation, and modelling in real situations.',
        '_mode': 'stable_professional_en'
    }


app_module.build_content = stable_content


def improved_set_cell_text(cell, text: str, lang: str = 'en', size: float = 8.0, bold: bool = False) -> None:
    rtl = lang == 'ar'
    font = 'Arial' if rtl else 'Times New Roman'
    cell.text = ''
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    text = clean_text(text)
    lines = text.split('\n') if text else ['']
    for i, line in enumerate(lines):
        line = line.strip()
        if rtl and re.match(r'^\d+[\.)]\s+', line):
            line = RLM + line  # English digits stay; RTL paragraph places them on the right.
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        app_module.set_paragraph_bidi(paragraph, rtl)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.0
        run = paragraph.add_run(line)
        effective_size = max(size + 0.35, 7.1 if rtl else 7.0)
        app_module.set_run_font(run, font, effective_size, bold=True)


app_module.set_cell_text = improved_set_cell_text


def fallback_docx(lesson, reason=''):
    content = stable_content(lesson)
    doc = Document()
    doc.core_properties.title = f"Lesson Plan - {lesson.topic}"
    doc.core_properties.author = lesson.teacher or 'Magdy Lesson Planner'
    title = doc.add_heading('Magdy Lesson Planner - Lesson Plan', 0)
    title.alignment = 1
    for title_text, key in [('Teacher', 'teacher'), ('Topic', 'topic')]:
        doc.add_paragraph(f"{title_text}: {getattr(lesson, key, '')}")
    for title_text, key in [('Learning Outcomes', 'learning_outcomes'), ('Success Criteria', 'success_criteria'), ('Starter', 'starter'), ('Main Activities', 'main'), ('Teacher-led', 'teacher_led'), ('Student-led', 'student_led'), ('Plenary', 'plenary')]:
        p = doc.add_paragraph()
        r = p.add_run(title_text)
        r.bold = True
        doc.add_paragraph(content.get(key, ''))
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


def safe_preview():
    try:
        lessons, errors = parse_lessons_from_request()
        if errors:
            return jsonify({'ok': False, 'errors': errors, 'status': status_payload()}), 400
        lesson = lessons[0]
        content = stable_content(lesson)
        return jsonify({'ok': True, 'lesson': asdict(lesson), 'content': content, 'status': status_payload()})
    except Exception as exc:
        logger.exception('Safe preview failed')
        return jsonify({'ok': False, 'error': 'تعذر إنشاء المعاينة. تم تسجيل الخطأ في Render Logs.', 'details': str(exc), 'status': status_payload()}), 500


def safe_generate():
    try:
        lessons, errors = parse_lessons_from_request()
        if errors:
            return Response(' | '.join(errors), status=400, mimetype='text/plain; charset=utf-8')
        user_key = lessons[0].teacher or request.remote_addr or 'anonymous'
        files = []
        for lesson in lessons:
            ok_limit, limit_msg = check_usage_limit(user_key)
            if not ok_limit:
                return Response(limit_msg, status=429, mimetype='text/plain; charset=utf-8')
            try:
                docx_bytes = app_module.generate_docx(lesson)
                try:
                    store_docx_file(lesson, docx_bytes)
                except Exception:
                    logger.exception('Could not store generated file in library; continuing download')
            except Exception as exc:
                logger.exception('Official template generation failed; using fallback DOCX')
                docx_bytes = fallback_docx(lesson, str(exc))
            files.append((_ascii_name(f'Lesson_Plan_{lesson.index}', 'docx'), docx_bytes))
        if len(files) == 1:
            filename, docx_bytes = files[0]
            return send_file(io.BytesIO(docx_bytes), mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name=filename, max_age=0)
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename, docx_bytes in files:
                zf.writestr(filename, docx_bytes)
        zip_bytes.seek(0)
        return send_file(zip_bytes, mimetype='application/zip', as_attachment=True, download_name=_ascii_name('Lesson_Plans_Batch', 'zip'), max_age=0)
    except Exception as exc:
        logger.exception('Safe generate failed')
        return Response(f'Internal generation error. Render Logs details: {exc}', status=500, mimetype='text/plain; charset=utf-8')


app.view_functions['preview'] = safe_preview
app.view_functions['generate'] = safe_generate


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': exc.description, 'status_code': exc.code, 'status': status_payload()}), exc.code
    if exc.code in (404, 405):
        return redirect(url_for('index'))
    return exc
