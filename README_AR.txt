Magdy Planning Studio - التطبيق المدمج
=====================================

هذا المشروع يدمج ثلاثة أنظمة داخل رابط واحد:
1) Lesson Planner: تحضير حتى 5 دروس مع معاينة وتصدير Word.
2) Medium Term Plan: توزيع المحتوى على 14 أسبوعًا داخل قالب المدرسة الرسمي.
3) Long Term Plan: توزيع العام على HT1 إلى HT6 داخل قالب المدرسة الرسمي.

الصفحة الرئيسية:
- /                     لوحة اختيار نوع التخطيط
- /lesson-planner       تحضير الدروس
- /curriculum-planner   خطط MTP / LTP
- /library              مكتبة تحضير الدروس

تشغيل محلي:
1) ثبّت Python 3.10 أو أحدث.
2) نفّذ: pip install -r requirements.txt
3) انسخ .env.example إلى .env وأضف OPENAI_API_KEY.
4) نفّذ: python app.py
5) افتح: http://127.0.0.1:5000

النشر على Render:
- Build Command:
  pip install -r requirements.txt
- Start Command:
  gunicorn expert_entry:app --bind 0.0.0.0:$PORT --timeout 180
- Environment Variables:
  OPENAI_API_KEY
  OPENAI_MODEL=gpt-5.5
  FLASK_SECRET
  DAILY_TOTAL_LIMIT=300
  DAILY_USER_LIMIT=25

ملاحظات مهمة:
- لا تحذف expert_entry.py لأن Render يعتمد عليه لتشغيل محرك التحضير المتقدم.
- قوالب Word موجودة في assets و word_templates.
- يعمل النظام بوضع Smart Offline Mode عند غياب مفتاح الذكاء الاصطناعي.
- تصدير Word يعمل على Render مباشرة.
- تصدير PDF يحتاج LibreOffice مثبتًا على الخادم؛ لذلك قد لا يعمل في خطة Render المجانية.
- الملفات المؤقتة للخطط تحفظ في generated_plans وتحذف تلقائيًا بعد 24 ساعة.
- ملفات تحضير الدروس تحفظ في generated_lessons.
