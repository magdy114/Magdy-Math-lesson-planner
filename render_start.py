from dataclasses import asdict
from datetime import datetime
import io
import zipfile

from werkzeug.exceptions import HTTPException
from flask import redirect, url_for, Response, request, jsonify, send_file
from docx import Document
from docx.shared import Pt

from app import (
    app,
    status_payload,
    parse_lessons_from_request,
    build_content,
    generate_docx,
    store_docx_file,
    check_usage_limit,
    logger,
)


@app.route('/favicon.ico')
def favicon():
    return Response(status=204)


@app.route('/generate', methods=['GET'], endpoint='generate_get')
def generate_get():
    return redirect(url_for('index'))


def _ascii_name(prefix='Lesson_Plan', ext='docx'):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


def _add_para(doc, title, text):
    p = doc.add_paragraph()
    r = p.add_run(str(title or ''))
    r.bold = True
    r.font.size = Pt(12)
    p2 = doc.add_paragraph(str(text or ''))
    p2.paragraph_format.space_after = Pt(6)


def fallback_docx(lesson, reason=''):
    """Create a valid Word file even if the official template fails on Render."""
    content = build_content(lesson)
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
        _add_para(doc, 'System note', 'Official template fallback was used. The lesson content is still generated professionally.')

    labels = [
        ('Key words', 'keywords'),
        ('Primary SDG Focus', 'sdg'),
        ('Strategies', 'strategies'),
        ('Intervention / Action Plan', 'intervention'),
        ('Learning Outcomes', 'learning_outcomes'),
        ('Differentiation', 'differentiation'),
        ('Success Criteria', 'success_criteria'),
        ('Starter', 'starter'),
        ('Main Activities', 'main'),
        ('Teacher-led', 'teacher_led'),
        ('Student-led', 'student_led'),
        ('Plenary', 'plenary'),
        ('KPI AFL Assignment Task', 'kpi'),
        ('Resources', 'resources'),
        ('UAE Identity / Sustainability', 'identity'),
        ('Competencies', 'competency'),
        ('Curriculum links', 'curriculum'),
    ]
    for title, key in labels:
        _add_para(doc, title, content.get(key, ''))

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


def safe_preview():
    """Preview endpoint that always returns JSON, even if AI/template code raises an error."""
    try:
        lessons, errors = parse_lessons_from_request()
        if errors:
            return jsonify({'ok': False, 'errors': errors, 'status': status_payload()}), 400
        lesson = lessons[0]
        content = build_content(lesson)
        return jsonify({'ok': True, 'lesson': asdict(lesson), 'content': content, 'status': status_payload()})
    except Exception as exc:
        logger.exception('Safe preview failed')
        return jsonify({
            'ok': False,
            'error': 'تعذر إنشاء المعاينة. تم تسجيل الخطأ في Render Logs.',
            'details': str(exc),
            'status': status_payload(),
        }), 500


def safe_generate():
    """Generate Word safely. Never return the browser's generic Internal Server Error page."""
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
                docx_bytes = generate_docx(lesson)
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
            return send_file(
                io.BytesIO(docx_bytes),
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                as_attachment=True,
                download_name=filename,
                max_age=0,
            )

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
        return jsonify({
            'ok': False,
            'error': exc.description,
            'status_code': exc.code,
            'status': status_payload(),
        }), exc.code
    if exc.code in (404, 405):
        return redirect(url_for('index'))
    return exc
