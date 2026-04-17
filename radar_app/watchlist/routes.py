"""Watchlist-related routes extracted from the legacy app module."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.shared.auth import login_required
from radar_app.shared.startup import ensure_db_ready
from radar_app.watchlist.service import (
    add_stock_and_start_analysis,
    build_performance_context,
    build_watchlist_context,
    update_watchlist_stock_status,
)


def register_watchlist_routes(app):
    @app.route('/watchlist')
    @login_required
    def watchlist_page():
        ensure_db_ready()
        return render_template('watchlist.html', **build_watchlist_context(session['user_id']))

    @app.route('/api/notification/<int:notif_id>/snooze', methods=['POST'])
    @login_required
    def notification_snooze(notif_id):
        db.snooze_notification(notif_id, session['user_id'])
        return jsonify({'ok': True})

    @app.route('/api/notification/<int:notif_id>/dismiss', methods=['POST'])
    @login_required
    def notification_dismiss(notif_id):
        db.dismiss_notification(notif_id, session['user_id'])
        return jsonify({'ok': True})

    @app.route('/add', methods=['POST'])
    @login_required
    def add_stock():
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        notes = request.form.get('desc', '').strip()
        market = request.form.get('market', '').strip()
        if not code or not name:
            flash('Stock code and name are required.', 'warning')
            return redirect(url_for('index'))

        code, market = add_stock_and_start_analysis(session['user_id'], code, name, market, notes)
        flash(f'{name} ({code}) 已添加，巴菲特正在分析中…', 'success')
        return redirect(url_for('watchlist_page'))

    @app.route('/remove/<code>', methods=['POST'])
    @login_required
    def remove_stock(code):
        db.remove_user_stock(session['user_id'], code)
        return redirect(url_for('watchlist_page'))

    @app.route('/api/stock/<code>/status', methods=['POST'])
    @login_required
    def update_stock_status(code):
        """移动卡片到 watching / holding / sold，记录日期和价格。"""
        payload = update_watchlist_stock_status(session['user_id'], code, request.get_json() or {})
        if not payload:
            return jsonify({'error': 'invalid status'}), 400
        return jsonify(payload)

    @app.route('/watchlist/performance')
    @login_required
    def performance_page():
        return render_template('performance.html', **build_performance_context(session['user_id']))
