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
    # English digits in both Arabic and English. RTL mark keeps 1., 2. at the right start of Arabic lines.
    if lang == 'ar':
        return '\n'.join(f"{RLM}{i}. {item}" for i, item in enumerate(items, 1))
    return '\n'.join(f"{i}. {item}" for i, item in enumerate(items, 1))


def math(s: str) -> str:
    # LaTeX-style math kept LTR inside Arabic text.
    return f"{LRM}\\({s}\\){LRM}"


def subject_family(subject: str) -> str:
    s = (subject or '').lower().strip()
    if any(x in s for x in ['لغة عربية', 'اللغه العربيه', 'عربي', 'arabic']):
        return 'arabic_language'
    if any(x in s for x in ['رياض', 'math', 'calculus', 'جبر', 'هندسة']):
        return 'mathematics'
    if any(x in s for x in ['science', 'علوم', 'biology', 'chemistry', 'physics', 'فيزياء', 'كيمياء', 'أحياء']):
        return 'science'
    if any(x in s for x in ['english', 'لغة انجليزية', 'انجليزي']):
        return 'english_language'
    if any(x in s for x in ['islamic', 'اسلام', 'إسلام']):
        return 'islamic'
    return 'general_subject'


def detect_special_topic(topic: str, subject: str, fam: str) -> str:
    t = (topic or '').lower()
    sf = subject_family(subject)
    if sf == 'arabic_language':
        if any(x in t for x in ['النعت', 'نعت', 'الصفة', 'صفة']):
            return 'arabic_naat'
        if any(x in t for x in ['المضاف', 'الإضافة', 'اضافة', 'المضاف إليه']):
            return 'arabic_idafa'
        if any(x in t for x in ['كان وأخواتها', 'كان', 'إن وأخواتها', 'ان واخواتها']):
            return 'arabic_grammar'
        if any(x in t for x in ['قراءة', 'نص', 'قصة', 'قصيدة', 'شعر']):
            return 'arabic_reading'
        return 'arabic_language'
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


def lesson_examples(topic: str, subject: str, lang: str, fam: str):
    special = detect_special_topic(topic, subject, fam)

    if lang == 'ar':
        if special == 'arabic_naat':
            return {
                'keywords': 'النعت، المنعوت، المطابقة، الإعراب، التذكير والتأنيث، الإفراد والتثنية والجمع، التعريف والتنكير',
                'concept': 'يركز الدرس على أن النعت تابع يصف اسمًا قبله يسمى المنعوت، ويتبعه في الإعراب والتعريف والتنكير والنوع والعدد. يميز الطلاب بين النعت والخبر من خلال موقع الكلمة ووظيفتها في الجملة.',
                'worked': 'مثال محلول: في جملة: «جاءَ الطالبُ المجتهدُ»، كلمة «المجتهدُ» نعت مرفوع؛ لأنها وصفت «الطالبُ» ووافقتْه في الرفع والتعريف والتذكير والإفراد. وفي جملة «قرأتُ قصةً ممتعةً» كلمة «ممتعةً» نعت منصوب لأنها وصفت «قصةً» ووافقتها في النصب والتنكير والتأنيث والإفراد.',
                'guided': 'تدريب موجه: استخرج النعت والمنعوت وبيّن علامة الإعراب في الجمل الآتية: «كرّمت المدرسةُ الطالباتِ المتميزاتِ»، «شاهدتُ منظرًا جميلًا»، «مررتُ بمعلمٍ مبدعٍ». ثم اطلب من الطلاب تحويل جملة مفردة إلى مثنى وجمع مع الحفاظ على المطابقة.',
                'hots': 'سؤال إثرائي: قارن بين «الطالبُ مجتهدٌ» و«الطالبُ المجتهدُ حاضرٌ». لماذا كانت «مجتهدٌ» خبرًا في الجملة الأولى، بينما «المجتهدُ» نعتًا في الثانية؟ ادعم إجابتك بتحليل نحوي قصير.',
                'misconception': 'الخلط بين النعت والخبر، أو نسيان مطابقة النعت للمنعوت في التعريف والتنكير أو الإعراب.'
            }
        if special == 'arabic_idafa':
            return {
                'keywords': 'المضاف، المضاف إليه، الجر، التعريف، التركيب الإضافي، المعنى',
                'concept': 'يتعرف الطلاب أن الإضافة تركيب يتكون من مضاف ومضاف إليه، ويكون المضاف إليه مجرورًا دائمًا، بينما يكتسب المضاف تعريفًا أو تخصيصًا من المضاف إليه.',
                'worked': 'مثال محلول: في «كتابُ الطالبِ مفيدٌ» كلمة «كتابُ» مضاف، و«الطالبِ» مضاف إليه مجرور بالكسرة. لا نقول «كتابُ الالطالبِ» لأن المضاف لا يقبل أل إذا أضيف.',
                'guided': 'تدريب موجه: حدد المضاف والمضاف إليه في: «بابُ المدرسةِ مفتوحٌ»، «دفترُ المعلمةِ منظمٌ»، ثم كوّن تركيبًا إضافيًا من كلمتين جديدتين.',
                'hots': 'سؤال إثرائي: كيف يتغير معنى الاسم عندما يصبح مضافًا؟ وضح بمثالين من الحياة المدرسية.',
                'misconception': 'إدخال أل على المضاف أو عدم جر المضاف إليه.'
            }
        if special == 'arabic_reading':
            return {
                'keywords': 'الفكرة الرئيسة، التفاصيل الداعمة، المعنى السياقي، الاستدلال، التذوق اللغوي',
                'concept': f'يركز درس {topic} على فهم النص وتحليل المعنى وبناء استنتاجات مدعومة بأدلة لغوية من النص.',
                'worked': 'مثال محلول: يقرأ المعلم فقرة قصيرة، يحدد الفكرة الرئيسة، ثم يضع خطًا تحت دليلين من النص يدعمان الفكرة.',
                'guided': 'تدريب موجه: يختار الطلاب جملة من النص ويشرحون دلالتها، ثم يربطونها بقيمة أو موقف من الحياة.',
                'hots': 'سؤال إثرائي: كيف كان سيتغير أثر النص لو اختار الكاتب عنوانًا آخر أو صورة مختلفة؟',
                'misconception': 'الاكتفاء بنسخ جملة من النص دون تفسير أو دليل.'
            }
        if special == 'tangent_arc':
            return {
                'keywords': 'المماس، ميل المماس، المشتقة، طول المنحنى، معدل التغير اللحظي، التكامل المحدد',
                'concept': f'يربط الدرس بين المشتقة كمعدل تغير لحظي وبين طول المنحنى كتراكم للمسافة على فترة. الصيغ الأساسية: {math("m=f'(a)")}، {math("y-f(a)=f'(a)(x-a)")}، {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
                'worked': f'مثال محلول: إذا كانت {math("f(x)=x^2+1")} عند {math("x=2")} فإن {math("f(2)=5")} و {math("f'(x)=2x")}، لذا {math("m=f'(2)=4")} ومعادلة المماس {math("y-5=4(x-2)")}. ثم نوضح أن طول المنحنى لا يساوي المسافة المستقيمة بين الطرفين بل يحسب بصيغة {math("L=\\int_a^b\\sqrt{1+(f'(x))^2}\\,dx")}.',
                'guided': f'تدريب موجه: للدالة {math("f(x)=x^2-3x")} عند {math("x=1")} أوجد {math("f'(1)")} واكتب معادلة المماس، ثم اشرح لماذا تدخل {math("f'(x)")} في صيغة طول المنحنى.',
                'hots': f'سؤال إثرائي: قارن بين ميل المماس عند نقطة واحدة وطول المنحنى على الفترة {math("[a,b]")}. أيهما قيمة لحظية وأيهما قيمة تراكمية؟',
                'misconception': 'الخلط بين \(f(a)\) و \(f′(a)\)، أو اعتبار طول المنحنى مساويًا للمسافة المستقيمة بين نقطتي البداية والنهاية.'
            }
        # Mathematics generic fallback
        return {
            'keywords': f'{topic}، مفاهيم أساسية، تطبيق، تفسير، تقويم',
            'concept': f'درس متخصص في {subject}: يربط الطلاب بين مفهوم {topic} والتطبيق العملي من خلال مثال محلول وتدريب موجه وسؤال تفكير عليا.',
            'worked': f'مثال محلول مرتبط مباشرة بموضوع {topic}: يحدد المعلم المفهوم، يوضح خطوات التفكير، ثم يبرز سبب اختيار القاعدة أو الاستراتيجية.',
            'guided': f'تدريب موجه على {topic}: يحل الطلاب مهمة مشابهة مع سؤال تفسير يوضح معنى الإجابة وليس الناتج فقط.',
            'hots': f'سؤال تفكير عليا: طبق فكرة {topic} في موقف جديد أو قارن بين حالتين مختلفتين وفسر الاختلاف.',
            'misconception': 'خطأ شائع مرتبط باختيار القاعدة أو تفسير الناتج.'
        }

    # English fallback
    return {
        'keywords': f'{topic}, key concepts, application, reasoning, assessment',
        'concept': f'Students build subject-specific understanding of {topic} in {subject} through a worked example, guided practice, and interpretation.',
        'worked': f'Worked example directly linked to {topic}, with clear steps, key vocabulary, and reasoning.',
        'guided': f'Guided practice on {topic} followed by an interpretation question.',
        'hots': f'HOTS: apply {topic} in a new context or compare two cases and justify the difference.',
        'misconception': 'A common misconception linked to method selection or interpretation.'
    }


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
    sf = subject_family(subject)

    if lang == 'ar':
        if sf == 'arabic_language':
            sdg = 'SDG 4 التعليم الجيد: تنمية الكفاءة اللغوية والتواصل الفعال، مع ربط اللغة بالهوية الوطنية والقيم الإيجابية في المجتمع المدرسي.'
            identity = 'الهوية الوطنية: توظيف أمثلة لغوية من بيئة دولة الإمارات وقيم الاحترام والتميز، مع تعزيز الاعتزاز باللغة العربية بوصفها وعاء الهوية والثقافة.'
            resources = 'نصوص قصيرة، بطاقات كلمات، سبورة ذكية، جمل تحليل نحوي، دفتر الطالب، بطاقات خروج، Classroom Monitor.'
        else:
            sdg = 'SDG 4 التعليم الجيد + SDG 11 مدن ومجتمعات مستدامة: توظيف المعرفة في قراءة النماذج الكمية واتخاذ قرارات دقيقة ومسؤولة.'
            identity = 'الهوية الوطنية والاستدامة: ربط الدقة والانضباط بثقافة التميز في دولة الإمارات واستخدام مثال يخدم التفكير المستدام.'
            resources = 'السبورة الذكية، ورقة عمل قصيرة، آلة حاسبة عند الحاجة، بطاقات خطوات، رسم بياني/جدول قيم، Classroom Monitor، دفتر الطالب.'
        return {
            'subject': subject,
            'class_name': class_name,
            'keywords': keywords,
            'sdg': sdg,
            'strategies': 'استراتيجية مخصصة للدرس: تمهيد تشخيصي، نموذج محلول، تفكير بصوت عالٍ، تدريب موجه، تطبيق مستقل قصير، سؤال HOTS، وتغذية راجعة فورية.' + (f'\nملاحظة المعلم: {note}' if note else ''),
            'intervention': 'خطة دعم: بطاقة خطوات، مثال جزئي، أسئلة تحقق قصيرة، وشريك داعم. إذا أخفق أكثر من 25% في AFL يتم تنفيذ إعادة تدريس قصيرة.\nخطأ متوقع: ' + ex['misconception'],
            'learning_outcomes': bullets([
                f'أفسر المفهوم الرئيس في درس {topic} باستخدام مصطلحات دقيقة مرتبطة بمادة {subject}.',
                'أميز القاعدة أو الفكرة المستهدفة من أمثلة صحيحة وأخرى خاطئة.',
                'أطبق المفهوم في مثال مباشر مع توضيح سبب كل خطوة.',
                'أحل نشاطًا متدرجًا مرتبطًا بعنوان الدرس وأستخدم لغة مناسبة للتبرير.',
                'أقارن بين حالتين أو مثالين وأفسر الفرق بينهما بدليل من الدرس.',
                'أصحح خطأً شائعًا مرتبطًا بالدرس وأكتب قاعدة مختصرة للتمييز.'
            ], 'ar'),
            'differentiation': bullets([
                'دعم: بطاقة خطوات + مثال جزئي + كلمات مفتاحية ملوّنة أو تمثيل بصري.',
                'مستوى متوقع: تدريب موجه ثم تطبيق مستقل مشابه للنموذج.',
                'متقدمون: سؤال HOTS يتطلب مقارنة أو تفسيرًا أو إنتاج مثال جديد.',
                'IEP/APL: تبسيط الصياغة، وقت إضافي، وتقليل الحمل الكتابي عند الحاجة.'
            ], 'ar'),
            'success_criteria': bullets([
                f'أشرح فكرة {topic} بجملة دقيقة.',
                'أحدد المصطلحات أو العناصر الأساسية دون خلط.',
                'أطبق القاعدة في مثال جديد.',
                'أبرر إجابتي بدليل واضح من المثال أو النص.',
                'أصحح خطأً شائعًا وأوضح سبب الخطأ.',
                'أحقق 80% فأكثر في بطاقة الخروج أو أكتب خطوة تحسين.'
            ], 'ar'),
            'starter': f'نشاط تمهيدي (5-7 دقائق): يعرض المعلم مثالين قصيرين مرتبطين بدرس {topic}؛ أحدهما صحيح والآخر يتضمن خطأ شائعًا. يحدد الطلاب الفرق ويبررون إجابتهم بكلمة مفتاحية من الدرس.\n{ex["guided"]}',
            'main': 'أنشطة رئيسية منظمة:\n' + bullets([ex['worked'], ex['guided'], 'تطبيق فردي قصير: ينتج الطالب مثالًا جديدًا أو يحل مهمة مشابهة ثم يقارن إجابته بزميله.', ex['hots']], 'ar'),
            'teacher_led': f'دور المعلم: يشرح المفهوم من مثال واضح، يبرز الكلمات المفتاحية والقاعدة، ويستخدم أسئلة تحقق قصيرة بعد كل خطوة.\n{ex["concept"]}',
            'student_led': 'دور الطلاب: يحلون تدريبًا موجهًا ثم تطبيقًا مستقلًا، يشرح كل طالب خطوة أو سببًا لزميله، ويكتب جملة تفسيرية توضح كيف وصل إلى الإجابة.',
            'plenary': 'خاتمة وتقويم: بطاقة خروج من 3 أجزاء: تحديد المفهوم، تطبيق قصير، وتصحيح خطأ شائع. يعرض المعلم إجابة نموذجية وخطوة تحسين.',
            'kpi': 'KPI AFL Task: 4 أسئلة قصيرة: مفهوم، تطبيق مباشر، تفسير، وتصحيح خطأ. معيار النجاح 80% فأكثر مع تدخل فوري لمن هم دون ذلك.',
            'resources': resources,
            'identity': identity,
            'competency': 'كفاءات: تواصل، تفكير ناقد، حل مشكلات، تعاون، إبداع، مسؤولية ذاتية، ووعي رقمي.',
            'curriculum': f'ارتباط المنهج: {subject} - {class_name} - {topic}. يتكامل مع الفهم، التطبيق، التفسير، التقويم، والتواصل الشفهي والكتابي.',
            '_mode': 'stable_professional_subject_specific'
        }

    return {
        'subject': subject,
        'class_name': class_name,
        'keywords': keywords,
        'sdg': 'SDG 4 Quality Education: applying subject knowledge through communication, reasoning, and responsible learning.',
        'strategies': 'Lesson-specific strategy: diagnostic starter, worked example, think-aloud modelling, guided practice, short independent application, HOTS question, and immediate feedback.' + (f'\nTeacher note: {note}' if note else ''),
        'intervention': 'Support plan: step card, partial worked example, short check questions, and supportive peer. If more than 25% miss the AFL task, reteach briefly.\nLikely misconception: ' + ex['misconception'],
        'learning_outcomes': bullets([f'Explain the key concept in {topic} using accurate {subject} terminology.', 'Identify the target rule or idea from correct and incorrect examples.', 'Apply the concept in a direct example with justification.', 'Complete a progressive task linked to the lesson title.', 'Compare two cases and explain the difference using lesson evidence.', 'Correct a common misconception and write a concise rule.'], 'en'),
        'differentiation': bullets(['Support: step card, partial example, coloured keywords, or visual representation.', 'Expected level: guided practice followed by a similar independent task.', 'Advanced learners: HOTS task requiring comparison, interpretation, or a new example.', 'IEP/APL: simplified wording, additional time, and reduced writing load when needed.'], 'en'),
        'success_criteria': bullets([f'I can explain {topic} accurately.', 'I can identify the key elements without confusion.', 'I can apply the rule or idea in a new example.', 'I can justify my answer with clear evidence.', 'I can correct a common error and explain why.', 'I can score at least 80% in the exit ticket or write an improvement step.'], 'en'),
        'starter': f'Starter (5-7 min): show two short examples linked to {topic}; one is correct and one includes a common error. Students identify the difference and justify their answer.\n{ex["guided"]}',
        'main': 'Organised main activities:\n' + bullets([ex['worked'], ex['guided'], 'Short independent application: students create a new example or solve a similar task, then compare with a peer.', ex['hots']], 'en'),
        'teacher_led': f'Teacher role: model the concept through a clear example, highlight key vocabulary/rule, and ask check questions after each step.\n{ex["concept"]}',
        'student_led': 'Student role: complete guided practice, solve an independent task, explain one reason to a peer, and write a short interpretation sentence.',
        'plenary': 'Plenary: 3-part Exit Ticket: identify the concept, apply it briefly, and correct a common error. Teacher shares a model answer and improvement step.',
        'kpi': 'KPI AFL Task: 4 short questions: concept, direct application, interpretation, and error correction. Success benchmark: 80% or higher with immediate intervention below benchmark.',
        'resources': 'Smart board, short worksheet, step cards, keywords, Classroom Monitor, student notebook.',
        'identity': 'Identity and values: connect learning to respect, excellence, clear communication, and responsible participation.',
        'competency': 'Competencies: communication, critical thinking, problem solving, collaboration, creativity, self-management, and digital awareness.',
        'curriculum': f'Curriculum link: {subject} - {class_name} - {topic}. Integrated with understanding, application, interpretation, assessment, and oral/written communication.',
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
            line = RLM + line
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
        app_module.set_paragraph_bidi(paragraph, rtl)
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.08
        run = paragraph.add_run(line)
        effective_size = max(size + 0.55, 7.35 if rtl else 7.0)
        app_module.set_run_font(run, font, effective_size, bold=True)


app_module.set_cell_text = improved_set_cell_text


def fallback_docx(lesson, reason=''):
    content = stable_content(lesson)
    doc = Document()
    doc.core_properties.title = f"Lesson Plan - {lesson.topic}"
    doc.core_properties.author = lesson.teacher or 'Magdy Lesson Planner'
    doc.add_heading('Magdy Lesson Planner - Lesson Plan', 0)
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
