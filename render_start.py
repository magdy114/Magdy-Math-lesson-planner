from dataclasses import asdict
from datetime import datetime
import io
import zipfile

from werkzeug.exceptions import HTTPException
from flask import redirect, url_for, Response, request, jsonify, send_file
from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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


@app.route('/favicon.ico')
def favicon():
    return Response(status=204)


@app.route('/generate', methods=['GET'], endpoint='generate_get')
def generate_get():
    return redirect(url_for('index'))


def _ascii_name(prefix='Lesson_Plan', ext='docx'):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


def ar_num(n: int) -> str:
    return str(n).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))


def bullets(items, lang='ar'):
    if lang == 'ar':
        return '\n'.join(f"{ar_num(i)}) {item}" for i, item in enumerate(items, 1))
    return '\n'.join(f"{i}. {item}" for i, item in enumerate(items, 1))


def detect_special_topic(topic: str, fam: str) -> str:
    t = (topic or '').lower()
    if any(x in t for x in ['طول المنحنى', 'arc length', 'curve length']) and any(x in t for x in ['مماس', 'tangent']):
        return 'tangent_arc'
    if any(x in t for x in ['طول المنحنى', 'arc length', 'curve length']):
        return 'arc_length'
    if any(x in t for x in ['مماس', 'tangent']):
        return 'tangent'
    return fam


def examples_for(topic: str, lang: str, fam: str):
    special = detect_special_topic(topic, fam)
    if lang == 'ar':
        bank = {
            'tangent_arc': {
                'keywords': 'المماس، ميل المماس، المشتقة، طول المنحنى، معدل التغير، التكامل العددي',
                'concept': 'يربط الطلاب بين المشتقة بوصفها ميل المماس وبين طول المنحنى بوصفه مجموعًا تراكميًا لعناصر صغيرة من المسافة.',
                'worked': 'مثال محلول: إذا كانت f(x)=x²+1 عند x=2 فإن الميل m=f′(2)=4، ومعادلة المماس y-5=4(x-2). ثم نناقش فكرة طول المنحنى من خلال L=∫√(1+(f′(x))²)dx.',
                'guided': 'تدريب موجه: أوجد ميل المماس للدالة f(x)=x²-3x عند x=1، ثم صف لفظيًا كيف يمكن تقدير طول المنحنى بين قيمتين باستخدام قطع مستقيمة قصيرة.',
                'hats': 'تحدي HOTS: أيهما يتغير أكثر عند زيادة الفترة: ميل المماس عند نقطة واحدة أم طول المنحنى على فترة؟ برر بإشارة إلى الرسم.',
                'misconception': 'الخلط بين طول القطعة المستقيمة بين نقطتين وطول المنحنى الحقيقي، أو استخدام قيمة الدالة بدل المشتقة لإيجاد الميل.'
            },
            'arc_length': {
                'keywords': 'طول المنحنى، التكامل، المشتقة، التراكم، التقدير العددي، المسافة',
                'concept': 'يفهم الطلاب أن طول المنحنى يقاس بتجميع أطوال قطع صغيرة جدًا، وأن المشتقة تساعد في بناء صيغة الطول.',
                'worked': 'مثال محلول: نرسم منحنى بسيطًا ونقسم الفترة إلى أجزاء، ثم نوضح أن L≈Σ√((Δx)²+(Δy)²)، وبعدها نربطها بصيغة التكامل L=∫√(1+(y′)²)dx.',
                'guided': 'تدريب موجه: قدّر طول منحنى من جدول قيم باستخدام ثلاث قطع مستقيمة، ثم قارن النتيجة بطول القطعة الواحدة بين البداية والنهاية.',
                'hats': 'تحدي HOTS: لماذا يزيد طول المنحنى غالبًا عن المسافة المستقيمة بين طرفيه؟ ادعم إجابتك برسم صغير.',
                'misconception': 'اعتبار طول المنحنى مساويًا للمسافة الأفقية أو المسافة المستقيمة بين نقطتي البداية والنهاية.'
            },
            'tangent': {
                'keywords': 'المماس، المشتقة، ميل المماس، معدل التغير اللحظي، معادلة الخط',
                'concept': 'يفسر الطلاب المشتقة عند نقطة على أنها ميل المماس ومعدل تغير لحظي، ثم يكتبون معادلة المماس بدقة.',
                'worked': 'مثال محلول: إذا كانت f(x)=x²+1 وعند x=2، فإن f(2)=5 و f′(2)=4؛ إذن معادلة المماس y-5=4(x-2).',
                'guided': 'تدريب موجه: أوجد ميل المماس ومعادلته للدالة f(x)=x²-3x عند x=1، مع توضيح الفرق بين f(1) و f′(1).',
                'hats': 'تحدي HOTS: إذا كان المماس أفقيًا عند نقطة، ماذا يعني ذلك عن المشتقة؟ وكيف يظهر ذلك على الرسم؟',
                'misconception': 'استخدام قيمة الدالة بدل قيمة المشتقة عند إيجاد ميل المماس.'
            },
        }
        if special in bank:
            return bank[special]
        generic = {
            'derivatives': ('المشتقة، الميل، معدل التغير، التمثيل البياني', 'مثال محلول: اشتق دالة كثيرة حدود بسيطة ثم فسر معنى المشتقة عند نقطة من الرسم.', 'تدريب موجه: يطبق الطلاب قاعدة القوى ثم يفسرون الإشارة الموجبة أو السالبة للمشتقة.', 'الخلط بين قيمة الدالة وقيمة المشتقة.'),
            'limits': ('النهاية، الاقتراب، الاتصال، التحليل، السلوك البياني', 'مثال محلول: استخدم جدول قيم حول نقطة ثم تحقق جبريًا بالتعويض أو التحليل.', 'تدريب موجه: حدد النهاية من رسم بياني ثم قارنها بقيمة الدالة عند النقطة.', 'اعتقاد أن النهاية تساوي دائمًا قيمة الدالة.'),
            'integrals': ('التكامل، المساحة، التراكم، الدالة الأصلية', 'مثال محلول: قدّر المساحة تحت منحنى بمستطيلات ثم اربطها بالتكامل المحدد.', 'تدريب موجه: يحسب الطلاب تكاملًا بسيطًا ويفسرون الناتج كسياق تراكمي.', 'الخلط بين المساحة الهندسية والتكامل ذي الإشارة.'),
            'functions': ('الدوال، المجال، المدى، التحويلات، التمثيل البياني', 'مثال محلول: حلل مجال ومدى دالة من الرسم ثم صف التحويلات الأساسية.', 'تدريب موجه: يحدد الطلاب المجال والمدى ويكتبون تفسيرًا لفظيًا.', 'الخلط بين المجال والمدى أو ترتيب التحويلات.'),
            'trig': ('الدوال المثلثية، الزوايا، الراديان، الدائرة المثلثية', 'مثال محلول: حدد قيمة زاوية خاصة من الدائرة المثلثية مع الإشارة الصحيحة.', 'تدريب موجه: يحول الطلاب بين الدرجات والراديان ويحددون الربع.', 'الخلط بين الدرجات والراديان.'),
            'logs': ('اللوغاريتمات، الدوال الأسية، النمو، الخصائص', 'مثال محلول: حوّل بين الصورة الأسية واللوغاريتمية ثم طبق خاصية صحيحة.', 'تدريب موجه: حل معادلة لوغاريتمية مع التحقق من المجال.', 'استخدام log(a+b)=log a+log b خطأ.'),
            'general': (f'{topic}، مفاهيم أساسية، تبرير، حل مشكلات', f'مثال محلول مرتبط بدرس {topic} مع إبراز خطوات التفكير الرياضي.', f'تدريب موجه متدرج على {topic} ثم سؤال تفسير.', 'خطأ شائع يستنتجه المعلم من إجابات الطلاب في البداية.')
        }
        k, worked, guided, misc = generic.get(fam, generic['general'])
        return {'keywords': k, 'concept': f'يبني الطلاب فهمًا عميقًا لدرس {topic} من خلال الشرح الموجه والتدريب المتدرج والتفسير الرياضي.', 'worked': worked, 'guided': guided, 'hats': f'تحدي HOTS: صمم سؤالًا جديدًا على {topic} وفسر لماذا يحتاج إلى تفكير أعلى من مجرد التعويض.', 'misconception': misc}
    else:
        bank = {
            'tangent_arc': {
                'keywords': 'tangent line, tangent slope, derivative, arc length, rate of change, numerical integration',
                'concept': 'Students connect derivative as tangent slope with arc length as accumulated small distance elements along a curve.',
                'worked': 'Worked example: If f(x)=x²+1 at x=2, then m=f′(2)=4 and the tangent line is y-5=4(x-2). Then introduce L=∫√(1+(f′(x))²)dx as the arc-length model.',
                'guided': 'Guided practice: find the tangent slope for f(x)=x²-3x at x=1, then describe how to estimate curve length using short line segments.',
                'hats': 'HOTS challenge: Which changes more when the interval changes: tangent slope at one point or arc length over the interval? Justify using a graph.',
                'misconception': 'Confusing straight-line distance between endpoints with actual curve length, or using function value instead of derivative for slope.'
            },
            'arc_length': {
                'keywords': 'arc length, integral, derivative, accumulation, numerical estimate, distance',
                'concept': 'Students understand curve length as accumulation of many small distance segments and connect the derivative to the formula.',
                'worked': 'Worked example: partition a curve into small segments and show L≈Σ√((Δx)²+(Δy)²), then connect it to L=∫√(1+(y′)²)dx.',
                'guided': 'Guided practice: estimate curve length from a value table using three straight segments, then compare with endpoint distance.',
                'hats': 'HOTS challenge: Why is curve length usually greater than straight-line endpoint distance? Support with a sketch.',
                'misconception': 'Treating curve length as horizontal distance or straight-line endpoint distance.'
            },
            'tangent': {
                'keywords': 'tangent line, derivative, tangent slope, instantaneous rate of change, line equation',
                'concept': 'Students interpret the derivative at a point as tangent slope and instantaneous rate of change, then write tangent equations accurately.',
                'worked': 'Worked example: For f(x)=x²+1 at x=2, f(2)=5 and f′(2)=4, so the tangent line is y-5=4(x-2).',
                'guided': 'Guided practice: find tangent slope and equation for f(x)=x²-3x at x=1, explaining the difference between f(1) and f′(1).',
                'hats': 'HOTS challenge: If a tangent is horizontal at a point, what does that mean about the derivative and the graph?',
                'misconception': 'Using function value instead of derivative value as tangent slope.'
            },
        }
        if special in bank:
            return bank[special]
        generic = {
            'derivatives': ('derivative, slope, rate of change, graph interpretation', 'Worked example: differentiate a simple polynomial and interpret the derivative at a point from the graph.', 'Guided practice: apply the power rule and explain the sign of the derivative.', 'Confusing function value with derivative value.'),
            'limits': ('limit, approaching, continuity, factorisation, graph behaviour', 'Worked example: use a table near a point, then verify algebraically using substitution or factorisation.', 'Guided practice: identify a limit from a graph and compare it with function value.', 'Assuming a limit always equals the function value.'),
            'integrals': ('integral, area, accumulation, antiderivative', 'Worked example: estimate area under a curve using rectangles, then connect to definite integral.', 'Guided practice: compute a simple integral and interpret it as accumulation.', 'Confusing geometric area with signed integral.'),
            'functions': ('functions, domain, range, transformations, graphs', 'Worked example: analyse domain and range from a graph, then describe transformations.', 'Guided practice: identify domain/range and write a verbal interpretation.', 'Confusing domain/range or transformation order.'),
            'trig': ('trigonometric functions, angles, radians, unit circle', 'Worked example: identify a special-angle value from the unit circle with correct sign.', 'Guided practice: convert between degrees and radians and identify the quadrant.', 'Confusing degrees and radians.'),
            'logs': ('logarithms, exponential functions, growth, properties', 'Worked example: convert between exponential and logarithmic form, then apply a valid property.', 'Guided practice: solve a logarithmic equation while checking domain.', 'Using log(a+b)=log a+log b incorrectly.'),
            'general': (f'{topic}, key concepts, justification, problem solving', f'Worked example related to {topic} with clear mathematical thinking steps.', f'Guided practice on {topic} followed by an interpretation question.', 'A common misconception identified from starter responses.')
        }
        k, worked, guided, misc = generic.get(fam, generic['general'])
        return {'keywords': k, 'concept': f'Students build deep understanding of {topic} through guided explanation, progressive practice, and mathematical reasoning.', 'worked': worked, 'guided': guided, 'hats': f'HOTS challenge: design a new question on {topic} and justify why it requires more than substitution.', 'misconception': misc}


def stable_content(lesson):
    """Professional fast content for Render Free. No long API wait, but lesson-specific and print-ready."""
    lang = lesson.language
    fam = topic_family(lesson.topic, lesson.source_text)
    topic = (lesson.topic or ('الدرس' if lang == 'ar' else 'the lesson')).strip()
    subject = (lesson.subject or ('رياضيات' if lang == 'ar' else 'Mathematics')).strip()
    class_name = (lesson.class_name or ('الثاني عشر متقدم' if lang == 'ar' else 'Grade 12 Advanced')).strip()
    ex = examples_for(topic, lang, fam)
    extra_kw = source_keywords(lesson.source_text, lang)
    keywords = ex['keywords'] + (('، ' + extra_kw) if lang == 'ar' and extra_kw else (', ' + extra_kw) if extra_kw else '')
    note = lesson.notes.strip()

    if lang == 'ar':
        return {
            'subject': subject,
            'class_name': class_name,
            'keywords': keywords,
            'sdg': 'SDG 4 التعليم الجيد + SDG 11 مدن ومجتمعات مستدامة: استخدام الرياضيات في اتخاذ قرارات دقيقة، وقراءة النماذج الكمية المرتبطة بالاستدامة وجودة الحياة.',
            'strategies': 'استراتيجية درس احترافية: تمهيد بصري سريع، نموذج محلول، تفكير بصوت عالٍ، Think-Pair-Share، تدريب موجه، سؤال HOTS، وتغذية راجعة فورية بالألواح الصغيرة.' + (f'\nملاحظة المعلم: {note}' if note else ''),
            'intervention': 'خطة دعم داخل الحصة: بطاقة خطوات مختصرة، مثال جزئي للطلاب المحتاجين للدعم، سؤال تحقق بعد كل خطوة، وشريك داعم. إذا أخفق أكثر من 25٪ في سؤال AFL، يتم تنفيذ إعادة تدريس قصيرة لمدة 5 دقائق.\nخطأ متوقع: ' + ex['misconception'],
            'learning_outcomes': bullets([
                f'أفسر الفكرة الرئيسة في درس {topic} بلغة رياضية صحيحة.',
                f'أميز بين المفاهيم المرتبطة بالدرس وأستخدم الرمز الرياضي المناسب.',
                'أطبق القاعدة أو الإجراء المناسب في مثال مباشر بخطوات منظمة.',
                'أحل مسألة متدرجة تتطلب اختيار استراتيجية الحل المناسبة.',
                'أفسر الناتج لفظيًا أو بيانيًا وأتحقق من معقوليته.',
                'أصحح خطأً شائعًا وأبرر التصحيح بدليل رياضي.'
            ], 'ar'),
            'differentiation': bullets([
                'دعم: خطوات مرقمة + مثال جزئي + تقليل الحمل الحسابي عند الحاجة.',
                'مستوى متوقع: تدريب موجه ثم سؤال مستقل مشابه للنموذج.',
                'متقدمون: سؤال HOTS يتطلب تفسيرًا أو تعميمًا أو مقارنة.',
                'IEP/APL: تبسيط اللغة، وقت إضافي، واستخدام تمثيل بصري أو آلة حاسبة عند الحاجة.'
            ], 'ar'),
            'success_criteria': bullets([
                f'أستطيع شرح فكرة {topic} بجملة رياضية دقيقة.',
                'أستطيع اختيار القاعدة أو الاستراتيجية المناسبة دون تخمين.',
                'أستطيع كتابة خطوات منظمة وواضحة في الحل.',
                'أستطيع تفسير معنى الناتج وربطه بالرسم أو السياق.',
                'أستطيع اكتشاف خطأ شائع وتصحيحه.',
                'أحقق 80٪ فأكثر في Exit Ticket أو أكتب خطوة التحسين.'
            ], 'ar'),
            'starter': f'نشاط تمهيدي (5-7 دقائق): سؤال استرجاع سريع مرتبط بمتطلبات {topic}. يعرض المعلم إجابتين مختلفتين ويطلب من الطلاب تحديد الفكرة الصحيحة والخطأ المتوقع.\n{ex["guided"]}',
            'main': f'أنشطة رئيسية منظمة:\n{bullets([ex["worked"], ex["guided"], "تطبيق فردي قصير ثم مقارنة زوجية للحل والخطوات.", ex["hats"]], "ar")}',
            'teacher_led': f'دور المعلم: يقدم نموذجًا محلولًا واضحًا، يبرز الكلمات المفتاحية، يكتب السبب الرياضي لكل خطوة، ويستخدم أسئلة تحقق قصيرة بعد كل انتقال.\n{ex["concept"]}',
            'student_led': 'دور الطلاب: يحلون مثالًا موجهًا ثم سؤالًا مستقلًا، يشرح كل طالب خطوة واحدة لزميله، ويكتب الطلاب جملة تفسيرية توضح معنى الإجابة وليس الناتج فقط.',
            'plenary': 'خاتمة وتقويم: Exit Ticket من 3 أجزاء: سؤال مهاري، سؤال تفسير، وتصحيح خطأ شائع. يعرض المعلم إجابة نموذجية قصيرة ويحدد خطوة تحسين للحصة القادمة.',
            'kpi': 'KPI AFL Task: 4 أسئلة قصيرة على Classroom Monitor: (1) مفهوم أساسي، (2) تطبيق مباشر، (3) تفسير الناتج، (4) خطأ شائع. معيار النجاح: 80٪ فأكثر، ومعالجة فورية لمن هم دون ذلك.',
            'resources': 'السبورة الذكية، أوراق عمل قصيرة، آلة حاسبة عند الحاجة، بطاقات خطوات، رسم بياني أو جدول قيم، Classroom Monitor، ودفتر الطالب.',
            'identity': 'الهوية الوطنية والاستدامة: ربط الدقة الرياضية بثقافة الإنجاز في دولة الإمارات، واستخدام مثال كمي مرتبط بكفاءة الموارد أو التخطيط المستدام عند مناقشة النتائج.',
            'competency': 'إطار الكفاءات: تفكير ناقد، تعاون، تواصل رياضي، حل مشكلات، إبداع، مسؤولية ذاتية، ووعي رقمي.',
            'curriculum': f'ارتباط المنهج: {subject} - {class_name} - درس {topic}. يتكامل مع مهارات التحليل، التفسير، التمثيل البياني، واستخدام النماذج الرياضية في مواقف حقيقية.',
            '_mode': 'stable_professional_ar'
        }
    return {
        'subject': subject,
        'class_name': class_name,
        'keywords': keywords,
        'sdg': 'SDG 4 Quality Education + SDG 11 Sustainable Cities: using mathematics to make accurate decisions and interpret quantitative models linked to sustainability.',
        'strategies': 'Professional lesson sequence: visual starter, worked example, think-aloud modelling, Think-Pair-Share, guided practice, HOTS challenge, and immediate mini-whiteboard feedback.' + (f'\nTeacher note: {note}' if note else ''),
        'intervention': 'In-class support: step card, partially completed example, check-for-understanding after each step, and supportive peer. If more than 25% miss the AFL question, reteach for 5 minutes.\nLikely misconception: ' + ex['misconception'],
        'learning_outcomes': bullets([
            f'Explain the key idea of {topic} using accurate mathematical language.',
            'Identify the relevant concepts and use correct notation.',
            'Apply the appropriate rule or procedure in a direct example.',
            'Solve a progressive problem by choosing a suitable strategy.',
            'Interpret the result verbally or graphically and check reasonableness.',
            'Correct a common misconception and justify the correction.'
        ], 'en'),
        'differentiation': bullets([
            'Support: numbered steps, partially completed example, and reduced calculation load when needed.',
            'Expected level: guided practice followed by a similar independent question.',
            'Advanced learners: HOTS task requiring interpretation, generalisation, or comparison.',
            'IEP/APL: simplified wording, additional time, visual representation, or calculator support where appropriate.'
        ], 'en'),
        'success_criteria': bullets([
            f'I can explain the idea of {topic} accurately.',
            'I can select the correct rule or strategy without guessing.',
            'I can present organised solution steps.',
            'I can interpret the meaning of the answer in context or on a graph.',
            'I can identify and correct a common error.',
            'I can score at least 80% in the Exit Ticket or write an improvement step.'
        ], 'en'),
        'starter': f'Starter (5-7 min): retrieval question linked to prerequisites for {topic}. The teacher shows two different answers and students identify the correct reasoning and the likely error.\n{ex["guided"]}',
        'main': f'Organised main activities:\n{bullets([ex["worked"], ex["guided"], "Short individual application followed by paired comparison of solution steps.", ex["hats"]], "en")}',
        'teacher_led': f'Teacher role: model a clear worked solution, highlight key vocabulary, explain the mathematical reason for each step, and ask short checks after each transition.\n{ex["concept"]}',
        'student_led': 'Student role: complete guided practice, solve one independent question, explain one step to a peer, and write a short interpretation sentence explaining the answer.',
        'plenary': 'Plenary: 3-part Exit Ticket: skill question, interpretation question, and error correction. Teacher displays a concise model answer and identifies the next improvement step.',
        'kpi': 'KPI AFL Task: 4 short Classroom Monitor questions: (1) key concept, (2) direct application, (3) interpretation, (4) common error. Success benchmark: 80% or higher with immediate support below benchmark.',
        'resources': 'Smart board, short worksheet, calculator where needed, step cards, graph or value table, Classroom Monitor, and student notebook.',
        'identity': 'UAE identity and sustainability: connect mathematical precision to the UAE culture of excellence and include a quantitative example related to resource efficiency or sustainable planning.',
        'competency': 'Competency framework: critical thinking, collaboration, mathematical communication, problem solving, creativity, self-management, and digital awareness.',
        'curriculum': f'Curriculum link: {subject} - {class_name} - {topic}. Integrated with analysis, interpretation, graphing, and mathematical modelling in real situations.',
        '_mode': 'stable_professional_en'
    }


# Make app.py use professional fast content on Render Free.
app_module.build_content = stable_content


def improved_set_cell_text(cell, text: str, lang: str = 'en', size: float = 8.0, bold: bool = False) -> None:
    """Clearer table text: RTL Arabic alignment, Arabic-Indic numbering, and stronger font weight."""
    rtl = lang == 'ar'
    font = 'Arial' if rtl else 'Times New Roman'
    cell.text = ''
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    text = clean_text(text)
    lines = text.split('\n') if text else ['']
    for i, line in enumerate(lines):
        if rtl:
            line = line.strip()
            # Convert English-style list numbers at line start to Arabic-Indic numbers for right-side RTL display.
            import re
            m = re.match(r'^(\d+)[\.)]\s*(.*)$', line)
            if m:
                line = f"{ar_num(int(m.group(1)))}） {m.group(2)}"
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        app_module.set_paragraph_bidi(paragraph, rtl)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.0
        run = paragraph.add_run(line)
        # Slightly increase small template font sizes and make generated content bold for readability.
        effective_size = max(size + 0.4, 7.2 if rtl else 7.0)
        app_module.set_run_font(run, font, effective_size, bold=True)


app_module.set_cell_text = improved_set_cell_text


def _add_para(doc, title, text):
    p = doc.add_paragraph()
    r = p.add_run(str(title or ''))
    r.bold = True
    r.font.size = Pt(12)
    p2 = doc.add_paragraph(str(text or ''))
    p2.paragraph_format.space_after = Pt(6)


def fallback_docx(lesson, reason=''):
    """Create a valid Word file even if the official template fails on Render."""
    content = stable_content(lesson)
    doc = Document()
    doc.core_properties.title = f"Lesson Plan - {lesson.topic}"
    doc.core_properties.author = lesson.teacher or 'Magdy Lesson Planner'

    title = doc.add_heading('Magdy Lesson Planner - Lesson Plan', 0)
    title.alignment = 1
    meta = doc.add_table(rows=5, cols=2)
    meta.style = 'Table Grid'
    fields = [
        ('Teacher', lesson.teacher),
        ('Subject', lesson.subject or content.get('subject', 'Mathematics')),
        ('Class', lesson.class_name or content.get('class_name', 'Grade 12 Advanced')),
        ('Topic', lesson.topic),
        ('Periods', lesson.periods or '1 period (45 min)'),
    ]
    for i, (k, v) in enumerate(fields):
        meta.cell(i, 0).text = k
        meta.cell(i, 1).text = str(v or '')

    if reason:
        _add_para(doc, 'System note', 'Official template fallback was used. The lesson content is generated in stable professional mode.')

    labels = [
        ('Key words', 'keywords'), ('Primary SDG Focus', 'sdg'), ('Strategies', 'strategies'),
        ('Intervention / Action Plan', 'intervention'), ('Learning Outcomes', 'learning_outcomes'),
        ('Differentiation', 'differentiation'), ('Success Criteria', 'success_criteria'),
        ('Starter', 'starter'), ('Main Activities', 'main'), ('Teacher-led', 'teacher_led'),
        ('Student-led', 'student_led'), ('Plenary', 'plenary'), ('KPI AFL Assignment Task', 'kpi'),
        ('Resources', 'resources'), ('UAE Identity / Sustainability', 'identity'),
        ('Competencies', 'competency'), ('Curriculum links', 'curriculum'),
    ]
    for title, key in labels:
        _add_para(doc, title, content.get(key, ''))

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


def safe_preview():
    """Preview endpoint that always returns JSON quickly on Render Free."""
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
    """Generate Word safely and quickly. Avoid long AI calls on the Free Render instance."""
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


# Replace views imported from app.py with safer Render versions.
app.view_functions['preview'] = safe_preview
app.view_functions['generate'] = safe_generate


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': exc.description, 'status_code': exc.code, 'status': status_payload()}), exc.code
    if exc.code in (404, 405):
        return redirect(url_for('index'))
    return exc
