"""Stock detail and analysis-related routes extracted from the legacy app module."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.shared.auth import admin_required
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


def _demo_block():
    """Return 403 JSON when a demo user tries to trigger AI analysis."""
    if session.get("is_demo"):
        return jsonify({"error": "demo_readonly", "message": "Sign up to run your own analysis."}), 403
    return None


def register_stock_routes(app):
    def _stock_context(code):
        context = build_stock_page_context(code, session['user_id'])
        return context

    @app.route('/stock/<path:code>')
    @login_required
    def stock_page(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found. Add it to your watchlist first.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock/detail.html', **context)

    # Legacy tab URLs → redirect to single-scroll page with anchor
    @app.route('/stock/<path:code>/letter')
    @login_required
    def stock_letter(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#letter', 301)

    @app.route('/stock/<path:code>/signals')
    @login_required
    def stock_signals(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#market', 301)

    @app.route('/stock/<path:code>/fundamentals')
    @login_required
    def stock_fundamentals_page(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#fundamentals', 301)

    @app.route('/stock/<path:code>/events')
    @login_required
    def stock_events_page(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#events', 301)

    @app.route('/stock/<path:code>/radar')
    @login_required
    def stock_radar_page(code):
        return redirect(url_for('stock_page', code=code.upper()) + '#market', 301)

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
        if (blocked := _demo_block()): return blocked
        payload = start_stock_job(session['user_id'], code, start_pipeline_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/analyze-only/<code>', methods=['POST'])
    @login_required
    def api_analyze_only(code):
        if (blocked := _demo_block()): return blocked
        payload = start_stock_job(session['user_id'], code, start_quant_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/generate-letter/<code>', methods=['POST'])
    @login_required
    def api_generate_letter(code):
        if (blocked := _demo_block()): return blocked
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
        if (blocked := _demo_block()): return blocked
        payload = start_batch_analysis(session['user_id'], (request.get_json() or {}).get('codes', []))
        if not payload:
            return jsonify({'error': 'no codes'}), 400
        return jsonify(payload)

    @app.route('/api/rerun-all', methods=['POST'])
    @admin_required
    def api_rerun_all():
        return jsonify(start_rerun_all())

    @app.route('/api/stock/<path:code>/events', methods=['POST'])
    @admin_required
    def add_stock_event(code):
        payload, status = add_stock_event_record(code, request.get_json() or {})
        return jsonify(payload), status

    @app.route('/api/intention/<path:code>')
    @login_required
    def api_intention(code):
        """
        机构意向综合评分 — 实时计算（A股专用）。
        前兆信号现场拉取，行为信号从 DB 读取缓存。
        """
        code = code.upper().split(".")[0].zfill(6)
        if not (code.isdigit() and len(code) == 6):
            return jsonify({"error": "A股代码只支持6位数字"}), 400

        import json as _json
        from datetime import datetime

        import db
        from scripts.config import CN_TZ
        from scripts.institutional_radar import compute_intention_score
        from scripts.precursor_signals import fetch_precursor_signals

        # ── 从 DB 读取已有信号 ────────────────────────────────────────
        funds = db.get_fundamentals(code) or {}
        signals = funds.get("signals", {}) or {}

        # 北向趋势（从 market_data / signals 中读，格式兼容）
        northbound = signals.get("northbound", {}) or {}
        # 不是 northbound dict 直接是 market-level，需适配
        if isinstance(northbound, str):
            try:
                northbound = _json.loads(northbound)
            except Exception:
                northbound = {}

        # 股东人数（inst_quarterly 表）
        sh_row = db.get_inst_quarterly(code)
        shareholder = {}
        inst_top = signals.get("inst_top") or []
        if sh_row and sh_row.get("quarter"):
            pct = sh_row.get("sh_pct_change", 0) or 0
            shareholder = {
                code: {
                    "cnt": sh_row.get("shareholder_cnt", 0),
                    "pct_change": pct,
                    "quarter": sh_row.get("quarter", ""),
                    "signal": "",
                    # 把 inst_top 带进去，供 _classify_inst_sellers 使用
                    "inst_top": inst_top,
                    "inc": int(signals.get("inst_increased") or 0),
                    "dec": int(signals.get("inst_decreased") or 0),
                }
            }

        # 资金流（从 fund_flow 表）
        fund_flow_row = db.get_fund_flow(code)
        fund_flow = {code: fund_flow_row} if fund_flow_row else {}

        # 报价（从 price 表，只需 change）
        price_row = db.get_latest_price(code)
        stock_row = db.get_stock(code)
        stock_name = (stock_row or {}).get("name", code)
        quotes = {code: {"change": price_row.get("change_pct", 0) or 0,
                         "name": stock_name}} if price_row else {code: {"change": 0, "name": stock_name}}

        # ── 前兆信号：优先读缓存，force=1 时强制重拉 ────────────────
        force_refresh = request.args.get("force") == "1"
        from radar_app.data.market import get_precursor_cache, save_precursor_cache
        cached = get_precursor_cache(code) if not force_refresh else {}
        cache_age_h = cached.get("age_hours", 999)

        if cached and cache_age_h < 48:
            # 48 小时内的缓存直接用；首页加载已负责每日刷新
            stock_precursor = {
                "survey":        cached.get("survey", {}),
                "short_selling": cached.get("short_selling", {}),
                "participation": cached.get("participation", {}),
            }
            precursor = {code: stock_precursor}
            fetched_at_str = cached.get("fetched_at", "")[:16]
            from_cache = True
        else:
            # 完全没有缓存时才现场拉（加 30 秒超时保护）
            try:
                import signal as _sig

                def _timeout_handler(signum, frame):
                    raise TimeoutError("precursor fetch timeout")

                _sig.signal(_sig.SIGALRM, _timeout_handler)
                _sig.alarm(30)
                try:
                    precursor = fetch_precursor_signals([code])
                finally:
                    _sig.alarm(0)
            except Exception:
                precursor = {}
            stock_precursor = precursor.get(code, {})
            try:
                sv = stock_precursor.get("survey", {})
                sh = stock_precursor.get("short_selling", {})
                pa = stock_precursor.get("participation", {})
                score_val = float(sv.get("score", 0) or 0)
                save_precursor_cache(code, sv, sh, pa, score_val, is_active=True)
            except Exception:
                pass
            fetched_at_str = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")
            from_cache = False

        # ── 计算综合评分 ─────────────────────────────────────────────
        score_data = compute_intention_score(
            code,
            lhb={},
            northbound=northbound,
            insider_all={},
            block_trades={},
            shareholder=shareholder,
            repurchase={},
            fund_flow=fund_flow,
            quotes=quotes,
            precursor=precursor,
        )

        # ── 数据新鲜度 + 原始前兆数据（供 UI 显示详情）────────────────
        score_data["precursor_fetched_at"] = fetched_at_str
        score_data["precursor_from_cache"] = from_cache
        score_data["behavioral_note"] = (
            "行为信号（高管/龙虎榜/大宗）来自每日 pipeline；"
            "本次只拉取了前兆信号（调研热度/融券/机构参与度）。"
        )
        # 原始前兆数据传给前端，用于 survey events / participation 数值展示
        score_data["precursor_raw"] = {
            "survey":        stock_precursor.get("survey", {}),
            "short_selling": stock_precursor.get("short_selling", {}),
            "participation": stock_precursor.get("participation", {}),
        }

        # 信号快照：inst_top + 资金流数据，供前端叙事渲染
        fund_flow_row = fund_flow.get(code) or {}
        score_data["signals_snapshot"] = {
            "inst_increased":   int(signals.get("inst_increased") or 0),
            "inst_decreased":   int(signals.get("inst_decreased") or 0),
            "inst_top":         inst_top,
            "main_net":         fund_flow_row.get("main_net"),
            "main_ratio":       fund_flow_row.get("main_ratio"),
            "margin_balance":   signals.get("margin_balance"),
            "margin_change_pct": signals.get("margin_change_pct"),
            "margin_direction": signals.get("margin_direction"),
        }

        # inst_classification 用真实 inst_top 重算（compute 里没有 inst_top 时为空）
        from scripts.institutional_radar import _classify_inst_sellers
        score_data["inst_classification"] = _classify_inst_sellers(inst_top)

        # observations 重建（带完整 signals_snapshot）
        from scripts.institutional_radar import _build_observations
        score_data["observations"] = _build_observations(
            score_data.get("components", {}),
            score_data["precursor_raw"],
            score_data["inst_classification"],
            score_data["signals_snapshot"],
        )

        return jsonify(score_data)

    @app.route('/api/stock/<path:code>/bundle')
    @login_required
    def api_export_bundle(code):
        from scripts.export_bundle import build_export_bundle
        result = build_export_bundle(code.upper(), user_id=session.get('user_id'))
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    @app.route('/api/predict/<path:code>', methods=['POST'])
    @login_required
    def api_submit_prediction(code):
        """Record a user's directional prediction for a stock signal."""
        import json as _json
        from datetime import datetime
        from radar_app.data.core import get_conn, CN_TZ

        data = request.get_json() or {}
        direction = data.get('direction')
        if direction not in ('up', 'down', 'unsure'):
            return jsonify({'error': 'invalid direction'}), 400
        note = (data.get('note') or '')[:80]

        _VALID_SIGNAL_TYPES = {'margin', 'survey', 'participation', 'fund_flow',
                               'insider', 'northbound', 'block_trade', 'inst_hold', 'general'}
        signal_type = data.get('signal_type') or 'general'
        if signal_type not in _VALID_SIGNAL_TYPES:
            signal_type = 'general'

        predicted_outcome = data.get('predicted_outcome') or None
        if predicted_outcome not in ('confirms', 'fails', None):
            predicted_outcome = None

        # snapshot the current precursor cache for this code (best effort)
        pure = code.upper().split('.')[0].zfill(6)
        snap_json = None
        try:
            with get_conn() as c:
                row = c.execute(
                    "SELECT survey_json, short_json, partic_json FROM stock_precursor_cache "
                    "WHERE code=:code ORDER BY fetched_at DESC LIMIT 1", {"code": pure}
                ).fetchone()
                if row:
                    snap_json = _json.dumps({
                        'survey':   _json.loads(row['survey_json'] or 'null'),
                        'short':    _json.loads(row['short_json']  or 'null'),
                        'partic':   _json.loads(row['partic_json'] or 'null'),
                    })
        except Exception:
            pass

        now = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
        user_id = session.get('user_id')
        with get_conn() as c:
            c.execute(
                "INSERT INTO signal_predictions "
                "(user_id, code, created_at, direction, note, signal_snapshot, signal_type, predicted_outcome) "
                "VALUES (:uid,:code,:now,:dir,:note,:snap,:stype,:outcome)",
                {"uid": user_id, "code": pure, "now": now, "dir": direction, "note": note,
                 "snap": snap_json, "stype": signal_type, "outcome": predicted_outcome},
            )
        return jsonify({'ok': True})

    @app.route('/api/predict/<path:code>', methods=['GET'])
    @login_required
    def api_get_predictions(code):
        """Return the last 5 predictions the current user made for this stock."""
        from radar_app.data.core import get_conn
        pure = code.upper().split('.')[0].zfill(6)
        user_id = session.get('user_id')
        with get_conn() as c:
            rows = c.execute(
                "SELECT id, direction, note, created_at, correct, actual_return_5d, "
                "signal_type, predicted_outcome "
                "FROM signal_predictions "
                "WHERE user_id=:uid AND code=:code "
                "ORDER BY created_at DESC LIMIT 10",
                {"uid": user_id, "code": pure},
            ).fetchall()
        return jsonify([dict(r) for r in rows])
