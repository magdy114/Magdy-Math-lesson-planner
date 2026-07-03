from dataclasses import asdict

from werkzeug.exceptions import HTTPException
from flask import redirect, url_for, Response, request, jsonify

from app import app, status_payload, parse_lessons_from_request, build_content, logger


@app.route('/favicon.ico')
def favicon():
    return Response(status=204)


@app.route('/generate', methods=['GET'], endpoint='generate_get')
def generate_get():
    return redirect(url_for('index'))


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


# Replace the preview view imported from app.py with the safe JSON-only version.
app.view_functions['preview'] = safe_preview


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
