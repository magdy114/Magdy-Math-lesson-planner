from werkzeug.exceptions import HTTPException
from flask import redirect, url_for, Response, request, jsonify

from app import app, status_payload


@app.route('/favicon.ico')
def favicon():
    return Response(status=204)


@app.route('/generate', methods=['GET'], endpoint='generate_get')
def generate_get():
    return redirect(url_for('index'))


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
