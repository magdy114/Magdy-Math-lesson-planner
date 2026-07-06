from __future__ import annotations

import re
from typing import Any


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
MATH_LEAK_RE = re.compile(
    r"\b(?:mathematics?|mathematical|algebra(?:ic)?|calculus|derivative|integral|"
    r"equation|function value|domain and range|graphical representation|desmos|geogebra|"
    r"calculator|computational load)\b|(?:رياضيات|رياضي(?:ة|اً|ا)?|جبر|تفاضل|تكامل|مشتق|معادلات|آلة حاسبة)",
    re.I,
)


def _normal(value: str) -> str:
    text = str(value or "").casefold().strip()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text)


SUBJECT_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("math", ("mathematics", "maths", "math", "calculus", "algebra", "geometry", "رياضيات", "الرياضيات", "حساب", "جبر", "هندسه")),
    ("english", ("english language", "english", "language arts", "ela", "esl", "efl", "لغه انجليزيه", "اللغه الانجليزيه", "انجليزي")),
    ("arabic", ("arabic language", "arabic", "لغه عربيه", "اللغه العربيه", "عربي")),
    ("science", ("science", "physics", "chemistry", "biology", "environmental science", "علوم", "فيزياء", "كيمياء", "احياء")),
    ("social", ("social studies", "history", "geography", "civics", "humanities", "دراسات اجتماعيه", "تاريخ", "جغرافيا", "تربيه وطنيه")),
    ("ict", ("computer science", "computing", "information technology", "ict", "coding", "برمجه", "حاسوب", "تقنيه المعلومات")),
    ("business", ("business", "economics", "accounting", "enterprise", "اداره اعمال", "اقتصاد", "محاسبه")),
    ("islamic", ("islamic studies", "islamic education", "quran", "hadith", "تربيه اسلاميه", "دراسات اسلاميه", "قران", "حديث")),
    ("art", ("art", "visual arts", "design", "music", "دراما", "فنون", "تصميم", "موسيقي")),
    ("pe", ("physical education", "pe", "sport", "sports", "تربيه بدنيه", "رياضه بدنيه")),
]


INFERENCE_MARKERS: dict[str, tuple[str, ...]] = {
    "english": (
        "grammar", "reading comprehension", "main idea", "context clues", "vocabulary",
        "paragraph writing", "essay", "speaking", "listening", "pronunciation", "author's purpose",
        "inference", "parts of speech", "verb tense", "passive voice", "conditionals", "relative clauses",
    ),
    "arabic": ("نحو", "صرف", "بلاغه", "قراءه", "تعبير", "اعراب", "نعت", "مفعول", "فاعل"),
    "science": ("hypothesis", "experiment", "variables", "photosynthesis", "cell", "force", "energy", "reaction", "تجربه", "فرضيه", "خليه", "طاقه"),
    "social": ("primary source", "secondary source", "timeline", "civilization", "population", "map skills", "مصدر اولي", "حضاره", "خريطه"),
    "ict": ("algorithm", "programming", "python", "html", "database", "cybersecurity", "debugging", "خوارزميه", "برمجه"),
    "business": ("stakeholder", "market", "revenue", "profit", "demand", "supply", "ميزانيه", "سوق", "ربح"),
    "islamic": ("surah", "ayah", "hadith", "fiqh", "سوره", "ايه", "حديث", "فقه"),
}

MATH_STRONG_MARKERS = (
    "derivative", "differentiation", "integral", "calculus", "algebra", "polynomial",
    "trigonometry", "matrix", "vector", "asymptote", "quadratic", "factorisation",
    "مشتق", "اشتقاق", "تكامل", "نهايات", "جبر", "مصفوف", "متجه", "داله تربيعيه",
)


def detect_subject_family(subject: str, topic: str = "", source_text: str = "") -> str:
    """Treat the entered subject as authoritative; infer only when it is missing/unknown."""
    explicit = _normal(subject)
    if explicit:
        for family, aliases in SUBJECT_ALIASES:
            if any(alias in explicit for alias in aliases):
                return family
        return "general"

    evidence = _normal(f"{topic}\n{source_text[:5000]}")
    if not evidence:
        return "general"

    scores = {
        family: sum(1 for marker in markers if marker in evidence)
        for family, markers in INFERENCE_MARKERS.items()
    }
    math_score = sum(1 for marker in MATH_STRONG_MARKERS if marker in evidence)
    if re.search(r"(?:\b[xyz]\s*[=<>]|\d\s*[+*/^]\s*\d|lim\s*\(|∫|√)", evidence):
        math_score += 2
    scores["math"] = math_score
    family, score = max(scores.items(), key=lambda item: item[1])
    return family if score > 0 else "general"


def _canonical_subject(family: str, language: str, entered: str) -> str:
    if str(entered or "").strip():
        return str(entered).strip()
    ar = language == "ar"
    labels = {
        "math": ("الرياضيات", "Mathematics"),
        "english": ("اللغة الإنجليزية", "English Language"),
        "arabic": ("اللغة العربية", "Arabic Language"),
        "science": ("العلوم", "Science"),
        "social": ("الدراسات الاجتماعية", "Social Studies"),
        "ict": ("الحوسبة وتقنية المعلومات", "Computing / ICT"),
        "business": ("إدارة الأعمال", "Business Studies"),
        "islamic": ("التربية الإسلامية", "Islamic Studies"),
        "art": ("الفنون", "Arts"),
        "pe": ("التربية البدنية", "Physical Education"),
        "general": ("المادة الدراسية", "Subject"),
    }
    return labels.get(family, labels["general"])[0 if ar else 1]


def _numbered(items: list[str], language: str) -> str:
    prefix = "\u200f" if language == "ar" else ""
    return "\n".join(f"{prefix}{index}. {item}" for index, item in enumerate(items, 1))


def _english_strand(topic: str, source_text: str) -> str:
    text = _normal(f"{topic} {source_text[:5000]}")
    strands = [
        ("grammar", ("grammar", "tense", "passive", "active voice", "conditional", "relative clause", "modal", "punctuation", "parts of speech", "subject verb agreement")),
        ("writing", ("writing", "essay", "paragraph", "report", "email", "article", "narrative", "persuasive", "argumentative", "summary")),
        ("reading", ("reading", "comprehension", "main idea", "supporting detail", "inference", "author's purpose", "skimming", "scanning", "text evidence")),
        ("speaking_listening", ("speaking", "listening", "presentation", "debate", "dialogue", "conversation", "pronunciation", "fluency")),
        ("vocabulary", ("vocabulary", "context clues", "synonym", "antonym", "word formation", "prefix", "suffix", "collocation")),
        ("literature", ("poem", "poetry", "novel", "short story", "drama", "character", "theme", "figurative language", "metaphor", "simile")),
    ]
    for strand, markers in strands:
        if any(marker in text for marker in markers):
            return strand
    return "integrated"


def _english_plan(lesson) -> dict[str, str]:
    language = lesson.language
    ar = language == "ar"
    topic = lesson.topic.strip() or ("مهارات اللغة الإنجليزية" if ar else "English language skills")
    subject = _canonical_subject("english", language, lesson.subject)
    class_name = lesson.class_name.strip() or ("الصف المحدد" if ar else "Selected grade")
    strand = _english_strand(topic, lesson.source_text)

    profiles_en = {
        "grammar": {
            "keywords": "form, meaning, use, sentence pattern, accuracy, editing, self-correction",
            "focus": f"Use the target language structure in {topic} accurately and appropriately in meaningful spoken and written contexts.",
            "starter": "Display two contrasting sentences. Students notice the pattern, identify the difference, and predict the rule before formal explanation.",
            "model": "Worked language model: analyse a correct example for form, meaning, and use; then complete a think-aloud showing why the structure fits the context.",
            "guided": "Guided practice: students complete and transform sentences, justify each choice with the rule, and correct one deliberately constructed error.",
            "independent": "Independent application: write a short contextual response using the target structure at least three times, then edit with a success checklist.",
            "misconception": "using the correct form without matching the intended meaning or time reference",
        },
        "reading": {
            "keywords": "prediction, gist, main idea, supporting details, inference, text evidence, author's purpose",
            "focus": f"Read the selected text for meaning, identify key ideas, and support interpretations of {topic} with precise textual evidence.",
            "starter": "Use the title, image, and two key words to predict content and purpose; students record one prediction and one question.",
            "model": "Worked reading model: think aloud through one paragraph, annotate a key sentence, infer meaning, and cite the exact phrase that supports the inference.",
            "guided": "Guided practice: pairs answer gist, detail, vocabulary-in-context, and inference questions, highlighting evidence for every response.",
            "independent": "Independent application: write a concise response explaining the main idea and two supporting details using evidence from the text.",
            "misconception": "giving a personal opinion instead of an answer supported by the text",
        },
        "writing": {
            "keywords": "purpose, audience, organisation, topic sentence, cohesion, evidence, drafting, editing",
            "focus": f"Plan, draft, revise, and edit a coherent response for {topic}, matching purpose, audience, and agreed success criteria.",
            "starter": "Compare a strong and weak opening. Students identify which better matches the purpose and audience and explain why.",
            "model": "Worked writing model: jointly unpack the prompt, plan ideas, construct an effective opening, and improve cohesion through precise linking language.",
            "guided": "Guided practice: students build one paragraph from a shared plan, select evidence or details, and improve sentence variety with teacher feedback.",
            "independent": "Independent application: produce a short complete response, self-assess against the rubric, and revise one content feature and one language feature.",
            "misconception": "including relevant ideas without organising them for the stated purpose and audience",
        },
        "speaking_listening": {
            "keywords": "active listening, turn-taking, pronunciation, fluency, interaction, clarification, presentation",
            "focus": f"Communicate ideas about {topic} clearly, listen for key information, and respond appropriately using accurate language and interaction strategies.",
            "starter": "Play or read a brief model exchange. Students identify the speaker's purpose, one key detail, and one useful interaction phrase.",
            "model": "Worked communication model: demonstrate planning notes, pronunciation of key vocabulary, turn-taking, clarification, and a complete evidence-based response.",
            "guided": "Guided practice: pairs rehearse with role cards, use follow-up questions, and give feedback on clarity, accuracy, and interaction.",
            "independent": "Independent application: deliver a short response or dialogue and submit a listening record containing the partner's main point and supporting detail.",
            "misconception": "prioritising speed over clear meaning, accurate language, and active response to a partner",
        },
        "vocabulary": {
            "keywords": "meaning, context clues, word families, collocation, connotation, pronunciation, application",
            "focus": f"Infer, explain, and apply the target vocabulary in {topic} using context, word relationships, and accurate original sentences.",
            "starter": "Present target words inside a short context. Students infer meanings and underline the clues that informed each inference.",
            "model": "Worked vocabulary model: analyse context clues, word parts, pronunciation, collocation, and connotation before constructing an original sentence.",
            "guided": "Guided practice: sort words by meaning and usage, complete collocations, and explain why one distractor does not fit the context.",
            "independent": "Independent application: create a short connected response using the target words accurately, then peer-check meaning and collocation.",
            "misconception": "memorising a translation without understanding collocation, connotation, or grammatical behaviour",
        },
        "literature": {
            "keywords": "character, setting, theme, conflict, language choice, interpretation, textual evidence",
            "focus": f"Interpret {topic} by analysing language, character, structure, or theme and supporting each claim with relevant textual evidence.",
            "starter": "Display a short quotation. Students annotate one striking word, predict its effect, and connect it to character or theme.",
            "model": "Worked literary analysis: move from quotation to technique, explain the effect, and connect the evidence to a defensible interpretation.",
            "guided": "Guided practice: groups analyse different quotations and present a claim-evidence-explanation response for peer critique.",
            "independent": "Independent application: write one analytical paragraph that includes a clear claim, embedded evidence, and explanation of the writer's choice.",
            "misconception": "retelling events instead of analysing how textual choices create meaning",
        },
        "integrated": {
            "keywords": "communication, comprehension, vocabulary, language accuracy, response, reflection",
            "focus": f"Develop integrated English skills through purposeful comprehension, discussion, and accurate language application in {topic}.",
            "starter": "Use a short stimulus linked to the topic. Students identify what they understand, one key word, and one question for learning.",
            "model": "Worked language model: demonstrate how to understand the task, select useful evidence or vocabulary, and construct a complete accurate response.",
            "guided": "Guided practice: students complete a scaffolded comprehension or language task, compare responses, and improve one answer using feedback.",
            "independent": "Independent application: produce a short spoken or written response that demonstrates understanding, accurate vocabulary, and clear organisation.",
            "misconception": "responding with isolated words rather than a complete answer appropriate to the task and audience",
        },
    }
    p = profiles_en[strand]

    if ar:
        return {
            "subject": subject,
            "class_name": class_name,
            "keywords": f"English Language: {p['keywords']}",
            "sdg": "SDG 4 التعليم الجيد: تنمية التواصل متعدد اللغات، القراءة الناقدة، والتعبير المسؤول في سياقات محلية وعالمية.",
            "strategies": _numbered([
                f"تمهيد لغوي قصير مرتبط مباشرة بموضوع {topic} لكشف المعرفة السابقة وتحديد الاحتياج اللغوي.",
                "نمذجة واضحة للمهارة باستخدام Think Aloud مع التركيز على المعنى والاستخدام والدليل، وليس الحفظ المنفصل.",
                "تدريب موجه فردي وثنائي مع أسئلة تحقق فورية وتغذية راجعة محددة على المحتوى ودقة اللغة.",
                "تطبيق مستقل ينتج عنه دليل تعلم مكتوب أو شفهي، ثم مراجعة ذاتية وفق معايير نجاح معلنة.",
            ], "ar"),
            "intervention": _numbered([
                "الدعم الفوري: نموذج جزئي، بنك كلمات، إطار جملة، وتقليل حجم النص أو المهمة مع الحفاظ على الهدف.",
                f"الخطأ المتوقع: {p['misconception']}؛ يعالج بمثال مضاد وتصحيح موجه.",
                "إعادة التدريس: مجموعة مصغرة عند انخفاض الإتقان عن 75% مع نموذج جديد وتحقق سريع من الفهم.",
                "الإثراء: توسيع الإجابة، تحسين الأسلوب، أو تبرير الاختيار اللغوي باستخدام دليل من النص أو السياق.",
            ], "ar"),
            "learning_outcomes": _numbered([
                f"يحدد الغرض والمتطلبات اللغوية الأساسية في درس {topic} بدقة.",
                f"يفهم الكلمات والأفكار الرئيسة أو النمط اللغوي المرتبط بموضوع {topic}.",
                "يطبق المهارة المستهدفة في تدريب موجه مستخدمًا لغة إنجليزية مناسبة للسياق.",
                "ينتج استجابة إنجليزية مكتوبة أو شفهية منظمة تتضمن دليل أداء قابلًا للملاحظة.",
                "يبرر اختيارًا لغويًا أو تفسيرًا بالاعتماد على القاعدة أو السياق أو دليل من النص.",
                "يراجع استجابته ويصحح خطأً في المعنى أو التنظيم أو الدقة اللغوية وفق قائمة تحقق.",
            ], "ar"),
            "differentiation": _numbered([
                "دعم: نص أقصر أو نموذج جزئي وبنك كلمات وإطارات جمل وصور داعمة.",
                "المستوى المتوقع: تدريب موجه ثم مهمة مستقلة تحقق الهدف الأساسي للدرس.",
                "متقدمون: توسيع الاستجابة وتبرير الاختيارات وتحسين الدقة والأسلوب لجمهور محدد.",
                "IEP/APL: تعليمات مجزأة، وقت معالجة إضافي، استجابة شفهية بديلة، وشريك داعم.",
            ], "ar"),
            "success_criteria": _numbered([
                "أفهم المطلوب وأحدد الغرض أو الفكرة أو النمط اللغوي المستهدف.",
                "أستخدم المفردات الرئيسة بدقة وفي سياق مناسب.",
                "أقدم إجابة كاملة ومنظمة وليست كلمات منفصلة.",
                "أدعم إجابتي بقاعدة أو سياق أو دليل من النص عند الحاجة.",
                "أراجع عملي وأصحح خطأً واحدًا على الأقل باستقلالية.",
                "أحقق 80% فأكثر في مهمة الخروج وفق معايير الدقة والفهم والتواصل.",
            ], "ar"),
            "starter": p["starter"],
            "main": _numbered([p["model"], p["guided"], p["independent"], f"HOTS: justify how changing purpose, audience, context, or language choice would change the response in {topic}."], "en"),
            "teacher_led": "ينمذج المعلم المهارة باللغة الإنجليزية، يفكر بصوت مرتفع، يفحص الفهم بأسئلة محددة، ويقدم تغذية راجعة منفصلة على المعنى ودقة اللغة.",
            "student_led": "يقرأ الطلاب أو يستمعون أو يناقشون أو يكتبون وفق طبيعة الدرس، ثم ينتجون دليلاً تعلميًا واضحًا ويستخدمون قائمة تحقق للمراجعة الذاتية أو مراجعة الزميل.",
            "plenary": "Exit Ticket: استجابة قصيرة تقيس الفهم، تطبيقًا لغويًا مستقلًا، وتصحيح خطأ أو تبرير اختيار باستخدام اللغة الإنجليزية.",
            "kpi": "AFL: مهمة من ثلاثة أجزاء تقيس الفهم، الاستخدام المستقل، ودقة التواصل. معيار النجاح 80% مع تغذية راجعة تحدد الخطوة التالية.",
            "resources": "النص أو الكتاب المرفوع، سبورة تفاعلية، بطاقات مفردات، نموذج كتابة أو تحدث، قاموس متعلم، قائمة تحقق، ومنصة Classroom Monitor.",
            "identity": "الهوية الوطنية: توظيف نصوص أو مواقف تواصل تعكس قيم الإمارات والتسامح والاستدامة والتواصل المسؤول مع العالم.",
            "competency": "التواصل، القراءة الناقدة، التعاون، الإبداع، الثقافة الرقمية، التعلم الذاتي، والوعي الثقافي.",
            "curriculum": f"المادة: {subject} | الصف: {class_name} | المجال: {strand}\nروابط قبلية: المفردات والفهم وبناء الجملة.\nروابط لاحقة: تطبيق المهارة في قراءة أو كتابة أو تحدث أكثر استقلالية.",
        }

    return {
        "subject": subject,
        "class_name": class_name,
        "keywords": p["keywords"],
        "sdg": "SDG 4 Quality Education: develop multilingual communication, critical literacy, and responsible expression in local and global contexts.",
        "strategies": _numbered([
            f"Begin with a short language task directly connected to {topic} to activate prior knowledge and reveal the precise learning need.",
            "Model the target skill through a think-aloud that makes meaning, language choice, evidence, and the success process visible.",
            "Use individual and paired guided practice with immediate checks for understanding and specific feedback on content and language accuracy.",
            "Move to an independent spoken or written product, followed by self-assessment and one purposeful revision against shared criteria.",
        ], "en"),
        "intervention": _numbered([
            "Immediate support: reduce task load, provide a partial model, word bank, sentence frame, visual cue, or shorter text while preserving the objective.",
            f"Likely misconception: {p['misconception']}; address it through a counterexample, guided comparison, and immediate corrected application.",
            "Reteaching trigger: if mastery is below 75 percent, teach a five-minute focus group with a fresh model and an immediate check.",
            "Extension: require a more developed response, precise stylistic choice, or evidence-based justification for purpose, audience, and context.",
        ], "en"),
        "learning_outcomes": _numbered([
            f"Identify the purpose, success requirements, and key language demands of {topic} from the task or model.",
            f"Explain the central vocabulary, idea, text feature, or language pattern required for {topic} using accurate terminology.",
            "Apply the target English skill accurately during guided practice and explain the evidence or rule supporting each important choice.",
            "Produce an organised spoken or written English response that demonstrates comprehension, appropriate vocabulary, and clear communication.",
            "Analyse a model or peer response, identifying one effective feature and one improvement supported by the agreed criteria.",
            "Independently revise and improve meaning, organisation, vocabulary, or language accuracy and explain the reason for the change.",
        ], "en"),
        "differentiation": _numbered([
            "Support: use a shorter text or task, visual cues, a partial model, a word bank, sentence frames, and guided rehearsal.",
            "Expected level: complete scaffolded practice before producing an independent response that meets the core lesson objective.",
            "Advanced: extend ideas, justify language choices, adapt register for audience, and improve precision, cohesion, or interpretation.",
            "IEP/APL: chunk instructions, allow additional processing time, offer oral rehearsal or an alternative response mode, and use a supportive peer.",
        ], "en"),
        "success_criteria": _numbered([
            "I identify the task purpose and the English skill, idea, or language pattern being assessed.",
            "I use key vocabulary accurately and appropriately within a meaningful context.",
            "I produce a complete, organised response rather than isolated words or unsupported statements.",
            "I support my interpretation or language choice with a rule, context clue, model feature, or textual evidence.",
            "I use the checklist to identify and independently correct at least one meaningful weakness.",
            "I achieve at least 80 percent in the exit task for comprehension, communication, and language accuracy.",
        ], "en"),
        "starter": p["starter"],
        "main": _numbered([
            p["model"],
            p["guided"],
            p["independent"],
            f"HOTS: justify how a change in purpose, audience, context, evidence, or language choice would alter the response in {topic}.",
        ], "en"),
        "teacher_led": "The teacher models the English skill explicitly, thinks aloud, checks understanding with named questions, and gives separate feedback on meaning, organisation, and language accuracy.",
        "student_led": "Students read, listen, discuss, speak, or write as required, create an observable learning product, and use a checklist for peer or self-review before revision.",
        "plenary": "Exit Ticket: one comprehension check, one independent English application, and one error correction or evidence-based justification linked to the lesson objective.",
        "kpi": "AFL task: three parts measuring comprehension, independent application, and communication accuracy. Success is 80 percent, followed by specific next-step feedback.",
        "resources": "Uploaded text or coursebook, interactive board, vocabulary cards, reading or writing model, learner dictionary, success checklist, and Classroom Monitor.",
        "identity": "UAE identity link: use texts and communication contexts reflecting UAE values, tolerance, sustainability, cultural awareness, and responsible global communication.",
        "competency": "Communication, critical literacy, collaboration, creativity, digital literacy, self-management, and cultural awareness.",
        "curriculum": f"Subject: {subject} | Class: {class_name} | Strand: {strand}\nPrerequisite links: vocabulary, comprehension, and sentence construction.\nNext links: increasingly independent reading, writing, speaking, or listening application.",
    }


GENERIC_PROFILES = {
    "science": {
        "en": ("scientific vocabulary, observation, hypothesis, variables, evidence, conclusion", "observe or interpret evidence, explain the scientific idea, and justify a conclusion", "laboratory or simulation, diagrams, data table, safety guidance, worksheet"),
        "ar": ("المصطلحات العلمية، الملاحظة، الفرضية، المتغيرات، الدليل، الاستنتاج", "يلاحظ أو يفسر الأدلة ويشرح المفهوم العلمي ويبرر الاستنتاج", "تجربة أو محاكاة، رسوم توضيحية، جدول بيانات، تعليمات سلامة، ورقة عمل"),
    },
    "social": {
        "en": ("source, chronology, cause and consequence, perspective, evidence, citizenship", "analyse a source or map, explain relationships, and support a judgement with evidence", "primary and secondary sources, map, timeline, data, case study"),
        "ar": ("المصدر، التسلسل الزمني، السبب والنتيجة، وجهة النظر، الدليل، المواطنة", "يحلل مصدرًا أو خريطة ويفسر العلاقات ويدعم الحكم بالدليل", "مصادر أولية وثانوية، خريطة، خط زمني، بيانات، دراسة حالة"),
    },
    "ict": {
        "en": ("algorithm, input, process, output, testing, debugging, digital citizenship", "design or apply a digital process, test the result, and improve it through evidence", "computer, approved software, sample file, debugging checklist, digital safety guidance"),
        "ar": ("الخوارزمية، المدخلات، المعالجة، المخرجات، الاختبار، تصحيح الأخطاء، المواطنة الرقمية", "يصمم أو يطبق عملية رقمية ويختبر الناتج ويحسنه اعتمادًا على الدليل", "حاسوب، برنامج معتمد، ملف تطبيقي، قائمة تصحيح أخطاء، إرشادات أمان رقمي"),
    },
    "business": {
        "en": ("stakeholder, objective, cost, revenue, market, evidence, decision", "apply the business concept to a case, analyse evidence, and justify a responsible decision", "case study, financial or market data, decision matrix, calculator if relevant"),
        "ar": ("أصحاب المصلحة، الهدف، التكلفة، الإيراد، السوق، الدليل، القرار", "يطبق مفهوم الأعمال على حالة ويحلل الأدلة ويبرر قرارًا مسؤولًا", "دراسة حالة، بيانات مالية أو سوقية، مصفوفة قرار، آلة حاسبة عند الحاجة"),
    },
    "islamic": {
        "en": ("meaning, evidence, value, application, reflection, responsible conduct", "explain the teaching using appropriate evidence and apply the value to a responsible real-life situation", "Quran or Hadith text, approved textbook, concept map, reflection prompt"),
        "ar": ("المعنى، الدليل، القيمة، التطبيق، التأمل، السلوك المسؤول", "يفسر التوجيه مستندًا إلى دليل مناسب ويطبق القيمة في موقف حياتي مسؤول", "نص قرآني أو حديث، الكتاب المعتمد، خريطة مفاهيم، سؤال تأمل"),
    },
    "art": {
        "en": ("elements, technique, composition, interpretation, process, reflection", "analyse a model, apply the selected technique, and explain creative decisions", "visual or audio exemplars, practical materials, process checklist, reflection prompt"),
        "ar": ("العناصر، التقنية، التكوين، التفسير، العملية، التأمل", "يحلل نموذجًا ويطبق التقنية المختارة ويفسر قراراته الإبداعية", "نماذج بصرية أو صوتية، خامات عملية، قائمة متابعة، سؤال تأمل"),
    },
    "pe": {
        "en": ("technique, coordination, fitness, safety, teamwork, reflection", "perform the skill safely, apply feedback, and evaluate technique or teamwork", "safe activity space, equipment, demonstration model, observation checklist"),
        "ar": ("التقنية، التوافق، اللياقة، السلامة، العمل الجماعي، التأمل", "يؤدي المهارة بأمان ويطبق التغذية الراجعة ويقيم التقنية أو التعاون", "مساحة نشاط آمنة، أدوات، نموذج أداء، قائمة ملاحظة"),
    },
    "arabic": {
        "en": ("meaning, vocabulary, structure, evidence, expression, editing", "understand the Arabic text or language feature and apply it accurately in communication", "Arabic text, vocabulary cards, language model, dictionary, editing checklist"),
        "ar": ("الفهم، المفردات، التركيب، الدليل، التعبير، المراجعة", "يفهم النص أو الظاهرة اللغوية ويطبقها بدقة في التواصل", "نص عربي، بطاقات مفردات، نموذج لغوي، معجم، قائمة مراجعة"),
    },
    "general": {
        "en": ("key concepts, evidence, application, reasoning, communication, reflection", "understand the central concept, apply it in a meaningful task, and justify the result", "uploaded source, coursebook, visual model, guided worksheet, success checklist"),
        "ar": ("المفاهيم الرئيسة، الدليل، التطبيق، الاستدلال، التواصل، التأمل", "يفهم المفهوم الرئيس ويطبقه في مهمة هادفة ويبرر الناتج", "المصدر المرفوع، الكتاب، نموذج بصري، ورقة موجهة، قائمة نجاح"),
    },
}


def _generic_non_math_plan(lesson, family: str) -> dict[str, str]:
    language = lesson.language
    ar = language == "ar"
    topic = lesson.topic.strip() or ("موضوع الدرس" if ar else "the lesson topic")
    subject = _canonical_subject(family, language, lesson.subject)
    class_name = lesson.class_name.strip() or ("الصف المحدد" if ar else "Selected grade")
    keywords, focus, resources = GENERIC_PROFILES.get(family, GENERIC_PROFILES["general"])["ar" if ar else "en"]

    if ar:
        return {
            "subject": subject,
            "class_name": class_name,
            "keywords": keywords,
            "sdg": "SDG 4 التعليم الجيد: تعلم قائم على الفهم والدليل والتطبيق المسؤول المرتبط بسياق دولة الإمارات.",
            "strategies": _numbered([f"تمهيد تشخيصي قصير مرتبط بدرس {topic}.", "نمذجة واضحة للمهارة أو المفهوم مع تفكير المعلم بصوت مرتفع.", "تدريب موجه وتعاوني مع أسئلة تحقق وتغذية راجعة فورية.", "تطبيق مستقل ينتج دليل تعلم قابلًا للملاحظة ثم مراجعة ذاتية."], "ar"),
            "intervention": _numbered(["دعم فوري بنموذج جزئي ومفردات أساسية وأسئلة مجزأة.", "معالجة التصور الخاطئ بمثال مضاد ومقارنة موجهة.", "إعادة تدريس قصيرة عند انخفاض الإتقان عن 75%.", "إثراء يتطلب تطبيقًا أعمق أو تبريرًا مدعومًا بالدليل."], "ar"),
            "learning_outcomes": _numbered([f"يحدد المفاهيم والمفردات الرئيسة في {topic}.", f"يفسر الفكرة أو العملية المركزية في {topic} باستخدام تمثيل مناسب.", focus + ".", "يحلل مثالًا أو مصدرًا ويستخرج دليلًا ذا صلة.", "ينتج تطبيقًا مستقلًا منظمًا يحقق متطلبات المهمة.", "يقيم جودة استجابته ويعدلها وفق معايير النجاح."], "ar"),
            "differentiation": _numbered(["دعم: نموذج جزئي ومفردات وصور وأسئلة قصيرة.", "المستوى المتوقع: تدريب موجه ثم تطبيق مستقل مباشر.", "متقدمون: مهمة متعددة الجوانب تتطلب التحليل والتبرير.", "IEP/APL: تعليمات مجزأة ووقت إضافي وطريقة استجابة بديلة."], "ar"),
            "success_criteria": _numbered(["أحدد المفهوم والمفردات المطلوبة.", "أشرح الفكرة بوضوح وبمصطلحات المادة.", "أطبق المهارة أو العملية بدقة.", "أستخدم دليلًا مناسبًا لدعم إجابتي.", "أراجع وأحسن جانبًا واحدًا باستقلالية.", "أحقق 80% فأكثر في مهمة الخروج."], "ar"),
            "starter": f"تمهيد: مصدر أو موقف قصير مرتبط بـ {topic}.\nسؤال تشخيصي: ماذا تعرف وما الدليل؟\nاستجابة متوقعة: فكرة أولية ومصطلح صحيح وسؤال للتعلم.",
            "main": _numbered([f"نموذج محلول/موضح: يعرض المعلم كيفية فهم وتنفيذ مهمة في {topic} مع توضيح القرارات.", f"تدريب موجه: يطبق الطلاب الخطوات على مثال جديد ويبررون كل اختيار.", f"تطبيق مستقل: ينتج كل طالب استجابة أو منتجًا قصيرًا يثبت تحقق الهدف.", f"HOTS: قارن بين تفسيرين أو طريقتين وحدد الأقوى اعتمادًا على الدليل."], "ar"),
            "teacher_led": "ينمذج المعلم الفكرة أو المهارة، يستخدم أسئلة تحقق محددة، يعالج التصور الخاطئ، ويقدم تغذية راجعة مرتبطة بمعايير النجاح.",
            "student_led": "ينفذ الطلاب مهمة فردية ثم تعاونية، يناقشون الأدلة، وينتجون استجابة قابلة للملاحظة والمراجعة.",
            "plenary": "بطاقة خروج: فهم المفهوم، تطبيق مستقل قصير، وتبرير أو تصحيح خطأ.",
            "kpi": "AFL: ثلاثة بنود تقيس الفهم والتطبيق والتبرير. معيار النجاح 80% مع تحديد خطوة المتابعة لكل طالب.",
            "resources": resources,
            "identity": "الهوية الوطنية: ربط التعلم بقيم الإمارات والمواطنة والاستدامة والابتكار والمسؤولية المجتمعية وفق طبيعة المادة.",
            "competency": "التفكير الناقد، التواصل، التعاون، حل المشكلات، الإبداع، والثقافة الرقمية.",
            "curriculum": f"المادة: {subject} | الصف: {class_name} | الدرس: {topic}\nروابط قبلية: المفردات والمفاهيم الأساسية.\nروابط لاحقة: تطبيق أكثر استقلالية وعمقًا.",
        }

    return {
        "subject": subject,
        "class_name": class_name,
        "keywords": keywords,
        "sdg": "SDG 4 Quality Education: evidence-informed, responsible learning connected to UAE contexts and global competence.",
        "strategies": _numbered([f"Begin with a brief diagnostic stimulus directly connected to {topic}.", "Model the concept or skill explicitly through a visible expert think-aloud.", "Use guided and collaborative practice with named checks and immediate feedback.", "Finish with an independent product, self-assessment, and one purposeful revision."], "en"),
        "intervention": _numbered(["Immediate support: partial model, essential vocabulary, chunked prompts, and a reduced task load.", "Address the likely misconception through a counterexample and guided comparison.", "Reteach in a five-minute focus group when mastery falls below 75 percent.", "Extend secure learners through deeper application or evidence-based justification."], "en"),
        "learning_outcomes": _numbered([f"Identify the central concepts and specialist vocabulary required for {topic}.", f"Explain the key idea or process in {topic} using an appropriate subject representation.", focus.capitalize() + ".", "Analyse an example, source, performance, or data set and select relevant evidence.", "Create an organised independent application that satisfies the task requirements.", "Evaluate the quality of the response and make a justified improvement using the criteria."], "en"),
        "differentiation": _numbered(["Support: partial model, essential vocabulary, visuals, and short graduated prompts.", "Expected level: guided rehearsal followed by a direct independent application.", "Advanced: multi-part task requiring analysis, transfer, and evidence-based justification.", "IEP/APL: chunk instructions, allow extra processing time, and offer an alternative response mode."], "en"),
        "success_criteria": _numbered(["I identify the required concept and specialist vocabulary.", "I explain the central idea clearly using subject-appropriate language.", "I apply the required skill or process accurately.", "I use relevant evidence to support my response.", "I independently review and improve one meaningful feature.", "I achieve at least 80 percent in the exit assessment."], "en"),
        "starter": f"Hook: a short source, example, demonstration, or scenario linked to {topic}.\nDiagnostic question: what do you notice, know, and need to find out?\nExpected response: one accurate observation, one key term, and one learning question.",
        "main": _numbered([f"Worked model: demonstrate how to interpret and complete a representative {topic} task while explaining each decision.", "Guided practice: students apply the process to a fresh example and justify important choices.", "Independent application: each student creates a short response or product that proves the objective has been met.", "HOTS: compare two interpretations, methods, or decisions and defend the stronger one using evidence."], "en"),
        "teacher_led": "The teacher models the concept or skill, uses named checks for understanding, treats the likely misconception, and gives criterion-linked feedback.",
        "student_led": "Students complete individual and collaborative tasks, discuss evidence, and create an observable response or product for review.",
        "plenary": "Exit Ticket: one concept check, one short independent application, and one justification or error correction.",
        "kpi": "AFL task: three items measuring understanding, application, and justification. Success is 80 percent, with a recorded next step for each learner.",
        "resources": resources,
        "identity": "UAE identity link: connect learning to UAE values, citizenship, sustainability, innovation, and responsible community participation as appropriate to the subject.",
        "competency": "Critical thinking, communication, collaboration, problem solving, creativity, digital literacy, and self-management.",
        "curriculum": f"Subject: {subject} | Class: {class_name} | Lesson: {topic}\nPrerequisite links: essential vocabulary and concepts.\nNext links: increasingly independent and complex application.",
    }


def _extract_items(value: str) -> list[str]:
    text = str(value or "").replace("\r", "\n").strip()
    if not text:
        return []
    text = re.sub(r"(?<!^)\s+(?=\d+[.)-]\s+)", "\n", text)
    items: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^[\s\u200e\u200f]*(?:\d+|[٠-٩]+)[.)-]?\s*", "", raw).strip(" •-–—")
        if line and line not in items:
            items.append(line)
    return items


def _ensure_numbered(value: str, fallback: str, count: int, language: str) -> str:
    items = _extract_items(value)
    for item in _extract_items(fallback):
        if len(items) >= count:
            break
        if item not in items:
            items.append(item)
    return _numbered(items[:count], language)


def _word_count(value: str) -> int:
    return len(re.findall(r"[\w\u0600-\u06ff]+", str(value or "")))


def adaptive_system_prompt(language: str) -> str:
    if language == "ar":
        return (
            "أنت خبير مناهج دولي لمدارس الإمارات. اسم المادة الذي أدخله المستخدم مرجع إلزامي ولا يجوز تغييره أو تحويله إلى الرياضيات. "
            "حلل المادة والصف وعنوان الدرس والنص المرفوع، ثم أنشئ خطة خاصة بتدريس تلك المادة فقط. "
            "لمادة اللغة الإنجليزية استخدم تربويات EFL/ESL المناسبة: reading, writing, grammar, vocabulary, speaking, listening, literature وفق عنوان الدرس، "
            "مع نمذجة لغوية وأمثلة ونصوص وأدلة تعلم، ومنع أي لغة رياضية أو أدوات مثل Desmos إلا إذا كانت المادة المدخلة رياضيات صراحة. "
            "للعلوم استخدم الاستقصاء والدليل، وللدراسات تحليل المصادر، وللحوسبة الخوارزميات والاختبار، ولكل مادة مصطلحاتها ومواردها. "
            "اكتب ستة نواتج تعلم وستة معايير نجاح وأربعة مستويات تمايز وأربعة أنشطة رئيسة، دون حشو أو تكرار، وبصياغة مناسبة لخلايا Word."
        )
    return (
        "You are an international curriculum and lesson-planning expert for UAE schools. The subject entered by the user is authoritative: never rename it or convert it to mathematics. "
        "Analyse the subject, grade, lesson title, teacher notes, and uploaded source, then use pedagogy, vocabulary, examples, activities, resources, and assessment native to that subject only. "
        "For English Language use EFL/ESL pedagogy appropriate to reading, writing, grammar, vocabulary, speaking, listening, or literature; include language modelling, meaningful context, and observable communication evidence. "
        "Do not use mathematical language, equations, Desmos, GeoGebra, calculators, algebraic/graphical representations, or computational differentiation unless the entered subject is explicitly Mathematics. "
        "For science use inquiry and evidence; for humanities use source analysis; for computing use algorithms, testing, and digital citizenship; adapt similarly for every discipline. "
        "Provide exactly six learning outcomes, six success criteria, four differentiation levels, and four main activities, all concise and suitable for an official Word table."
    )


def install(core, lesson_engine, lesson_density_patch) -> None:
    if getattr(core, "_subject_adaptive_patch_installed", False):
        return

    original_offline = core.offline_content
    original_enrich = lesson_density_patch._enrich

    def adaptive_offline(lesson):
        family = detect_subject_family(lesson.subject, lesson.topic, lesson.source_text)
        if family == "math":
            return original_offline(lesson)
        if family == "english":
            return _english_plan(lesson)
        return _generic_non_math_plan(lesson, family)

    def adaptive_enrich(lesson, output: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        family = detect_subject_family(lesson.subject, lesson.topic, lesson.source_text)
        if family == "math":
            return original_enrich(lesson, output, fallback)

        result = dict(output or {})
        fallback = dict(fallback or {})
        for field in (
            "strategies", "intervention", "starter", "main", "teacher_led", "student_led",
            "plenary", "kpi", "resources", "identity", "competency", "curriculum", "keywords", "sdg",
        ):
            current = str(result.get(field, ""))
            if not current or _word_count(current) < 4 or MATH_LEAK_RE.search(current):
                result[field] = fallback.get(field, current)

        result["learning_outcomes"] = _ensure_numbered(
            str(result.get("learning_outcomes", "")), str(fallback.get("learning_outcomes", "")), 6, lesson.language
        )
        result["success_criteria"] = _ensure_numbered(
            str(result.get("success_criteria", "")), str(fallback.get("success_criteria", "")), 6, lesson.language
        )
        result["differentiation"] = _ensure_numbered(
            str(result.get("differentiation", "")), str(fallback.get("differentiation", "")), 4, lesson.language
        )
        result["main"] = _ensure_numbered(
            str(result.get("main", "")), str(fallback.get("main", "")), 4, lesson.language
        )

        # Final contamination guard: any mathematics-only fallback is replaced field by field.
        for field, fallback_value in fallback.items():
            if field.startswith("_"):
                continue
            if MATH_LEAK_RE.search(str(result.get(field, ""))):
                result[field] = fallback_value

        result["subject"] = fallback.get("subject") or lesson.subject
        result["class_name"] = fallback.get("class_name") or lesson.class_name
        result["_density_qa"] = f"subject-adaptive-{family}-v1"
        return result

    core.offline_content = adaptive_offline
    core.topic_family = lambda topic, source_text="", subject="": detect_subject_family(subject, topic, source_text)
    lesson_engine.family = lambda subject: detect_subject_family(subject)
    lesson_engine.system_prompt = adaptive_system_prompt
    lesson_density_patch._enrich = adaptive_enrich
    try:
        lesson_engine.CACHE.clear()
    except Exception:
        pass
    core._subject_adaptive_patch_installed = True
