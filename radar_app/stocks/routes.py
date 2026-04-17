"""Stock detail and analysis-related routes extracted from the legacy app module."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.legacy.pipeline import (
    start_letter_job,
    start_news_update_job,
    start_pipeline_job,
    start_quant_job,
)
from radar_app.shared.auth import login_required
from radar_app.stocks.action_service import (
    add_stock_event_record,
    cancel_job,
    start_batch_analysis,
    start_rerun_all,
    start_stock_job,
)
from radar_app.stocks.service import (
    build_stock_page_context,
    get_job_payload,
    get_letter_payload,
)


def register_stock_routes(app):
    @app.route('/stock/<path:code>/fundamentals')
    @login_required
    def stock_fundamentals(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#tab-archive')

    @app.route('/stock/<path:code>')
    @login_required
    def stock_page(code):
        context = build_stock_page_context(code, session['user_id'])
        if not context:
            flash('Stock not found. Add it to your watchlist first.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock.html', **context)

    @app.route('/api/news/<code>')
    @login_required
    def api_news(code):
        return jsonify(db.get_news(code, days=7))

    @app.route('/api/letter/<code>')
    @login_required
    def api_letter(code):
        return jsonify(get_letter_payload(code))

    @app.route('/api/analyze/<code>', methods=['POST'])
    @login_required
    def api_analyze(code):
        payload = start_stock_job(session['user_id'], code, start_pipeline_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/analyze-only/<code>', methods=['POST'])
    @login_required
    def api_analyze_only(code):
        payload = start_stock_job(session['user_id'], code, start_quant_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/generate-letter/<code>', methods=['POST'])
    @login_required
    def api_generate_letter(code):
        payload = start_stock_job(session['user_id'], code, start_letter_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/refresh-news/<code>', methods=['POST'])
    @login_required
    def api_refresh_news(code):
        payload = start_stock_job(session['user_id'], code, start_news_update_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/job/<int:job_id>')
    @login_required
    def api_job(job_id):
        payload = get_job_payload(job_id)
        if not payload:
            return jsonify({'status': 'not_found'}), 404
        return jsonify(payload)

    @app.route('/api/job/<int:job_id>/cancel', methods=['POST'])
    @login_required
    def api_job_cancel(job_id):
        payload = cancel_job(job_id)
        if not payload:
            return jsonify({'error': 'not found'}), 404
        return jsonify(payload)

    @app.route('/api/analyze-batch', methods=['POST'])
    @login_required
    def api_analyze_batch():
        payload = start_batch_analysis(session['user_id'], (request.get_json() or {}).get('codes', []))
        if not payload:
            return jsonify({'error': 'no codes'}), 400
        return jsonify(payload)

    @app.route('/api/rerun-all', methods=['POST'])
    @login_required
    def api_rerun_all():
        if session.get('role') != 'admin':
            return jsonify({'error': 'forbidden'}), 403
        return jsonify(start_rerun_all())

    @app.route('/api/stock/<path:code>/events', methods=['POST'])
    @login_required
    def add_stock_event(code):
        if session.get('role') != 'admin':
            return jsonify({'error': 'forbidden'}), 403
        payload, status = add_stock_event_record(code, request.get_json() or {})
        return jsonify(payload), status
