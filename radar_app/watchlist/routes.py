"""Watchlist-related routes extracted from the legacy app module."""

import json
import ssl
import threading
import urllib.request
from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.data.core import get_conn
from radar_app.data.jobs import create_job, update_job
from radar_app.data.users import get_push_settings
from radar_app.shared.auth import login_required
from radar_app.shared.runtime import CN_TZ
from radar_app.watchlist.presenter import GRADE_UNRATED
from radar_app.shared.startup import ensure_db_ready
from radar_app.watchlist.service import (
    add_stock_and_start_analysis,
    build_performance_context,
    build_watchlist_context,
    update_watchlist_stock_status,
)


def _send_serverchan(key: str, title: str, content: str):
    try:
        ctx = ssl.create_default_context()
        payload = json.dumps({"title": title, "desp": content}).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{key}.send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, context=ctx, timeout=10)
    except Exception:
        pass


def _precursor_worker(job_id: int, user_id: int):
    logs = []

    def log(msg):
        logs.append(msg)
        update_job(job_id, status="running", log="\n".join(logs[-30:]))

    try:
        update_job(job_id, status="running")
        log("▶ 开始扫描前兆信号（调研 + 融券 + 参与度）…")

        from scripts.precursor_scan import run_precursor_scan
        result = run_precursor_scan()

        scanned = result.get("scanned", 0)
        active  = result.get("active", 0)
        log(f"✅ 完成：{scanned} 只扫描，{active} 只活跃")

        # 读缓存里的活跃股，生成推送内容
        with get_conn() as c:
            rows = c.execute(
                """
                SELECT p.code, s.name, p.score, p.survey_json, p.partic_json
                FROM stock_precursor_cache p
                LEFT JOIN stocks s ON s.code = p.code
                WHERE p.is_active = 1
                  AND p.fetched_at = (
                      SELECT MAX(fetched_at) FROM stock_precursor_cache WHERE code = p.code
                  )
                ORDER BY p.score DESC
                LIMIT 10
                """,
            ).fetchall()

        date_str = datetime.now(CN_TZ).strftime("%m-%d %H:%M")
        lines = [f"**机构雷达扫描** · {date_str}",
                 f"扫描 {scanned} 只 A 股，{active} 只有明显信号\n"]
        for row in rows:
            rec = dict(row)
            name = rec.get("name") or rec["code"]
            lines.append(f"**{name}（{rec['code']}）**")
            try:
                sv = json.loads(rec.get("survey_json") or "{}")
                events = sv.get("events") or []
                if events:
                    sp = [e for e in events if e.get("is_specific")]
                    latest = events[0]
                    kind = "专项调研" if sp else "参加会议"
                    lines.append(f"  📋 调研 {latest['date']} · {latest['n_inst']}家机构{kind}")
                else:
                    lines.append("  📋 调研 近期无记录")
            except Exception:
                pass
            try:
                pa = json.loads(rec.get("partic_json") or "{}")
                if pa.get("valid"):
                    latest_v = pa.get("latest", 0)
                    avg_v    = pa.get("avg_30d", 0)
                    trend    = pa.get("trend", "中性")
                    price_chg = pa.get("price_change_pct", 0.0)
                    chg_str  = f"+{price_chg:.1f}%" if price_chg >= 0 else f"{price_chg:.1f}%"
                    spike_flag = "⚡" if pa.get("spike") else ""
                    lines.append(f"  📊 参与度 {latest_v:.0f}（均值{avg_v:.0f}，趋势{trend}）{spike_flag} · 当日{chg_str}")
            except Exception:
                pass
            try:
                sh = json.loads(rec.get("short_json") or "{}")
                if sh.get("valid"):
                    lines.append(f"  📉 融券 {sh.get('desc', '')[:40]}")
            except Exception:
                pass
            lines.append("")  # 空行分隔

        push_settings = get_push_settings(user_id) or {}
        key = push_settings.get("wecom_webhook", "")
        if key:
            _send_serverchan(key, f"机构雷达 · {active} 只活跃", "\n".join(lines))
            log("📲 推送已发送")
        else:
            log("⚠️ 未配置 Server酱 SendKey，跳过推送")

        update_job(job_id, status="done", log="\n".join(logs[-30:]))

    except Exception as e:
        update_job(job_id, status="failed", error=str(e), log="\n".join(logs[-30:]))


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

    @app.route('/api/watchlist/add', methods=['POST'])
    @login_required
    def api_watchlist_add():
        """JSON 端点：从供应链卡片快速加股票到自选股并触发分析。"""
        data = request.get_json() or {}
        code = (data.get('code') or '').strip().upper()
        name = (data.get('name') or code).strip()
        if not code:
            return jsonify({'ok': False, 'error': 'missing code'}), 400
        from radar_app.data.stocks import get_watchlist_entry
        if get_watchlist_entry(session['user_id'], code):
            return jsonify({'ok': True, 'already': True})
        try:
            add_stock_and_start_analysis(session['user_id'], code, name, '', '')
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/add', methods=['POST'])
    @login_required
    def add_stock():
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        notes = request.form.get('desc', '').strip()
        market = request.form.get('market', '').strip()
        asset_type = request.form.get('asset_type', '').strip() or None
        if not code or not name:
            flash('Stock code and name are required.', 'warning')
            return redirect(url_for('index'))

        code, market = add_stock_and_start_analysis(session['user_id'], code, name, market, notes, asset_type=asset_type)
        type_label = f'（{asset_type}）' if asset_type and asset_type != '股票' else ''
        flash(f'{name}{type_label} ({code}) 已添加，正在分析中…', 'success')
        return redirect(url_for('watchlist_page'))

    @app.route('/remove/<code>', methods=['POST'])
    @login_required
    def remove_stock(code):
        db.remove_user_stock(session['user_id'], code)
        return redirect(url_for('watchlist_page'))

    @app.route('/api/stock/<code>/remove', methods=['DELETE'])
    @login_required
    def delete_stock(code):
        """htmx DELETE — soft-deletes from watchlist, returns empty so htmx swaps the element away."""
        db.remove_user_stock(session['user_id'], code)
        return '', 200

    @app.route('/api/stock/<code>/status', methods=['POST'])
    @login_required
    def update_stock_status(code):
        """移动卡片到 watching / holding / sold，记录日期和价格。"""
        payload = update_watchlist_stock_status(session['user_id'], code, request.get_json() or {})
        if not payload:
            return jsonify({'error': 'invalid status'}), 400
        return jsonify(payload)

    @app.route('/api/watchlist/filter')
    @login_required
    def api_watchlist_filter():
        """WHERE 1=1 dynamic server-side filter for watchlist stocks."""
        user_id = session['user_id']
        market = request.args.get('market')
        grade  = request.args.get('grade')

        # US-168：原来这里是
        #     LEFT JOIN (SELECT code, grade, MAX(id) AS id
        #                FROM analysis_results GROUP BY code) a
        # grade 既不在 GROUP BY 里也没被聚合。SQLite 容忍（随便挑一行，
        # 还不保证是 MAX(id) 那行），**Postgres 直接报错**：
        #     column "analysis_results.grade" must appear in the GROUP BY clause
        # 而这个 LEFT JOIN 是无条件拼进来的 —— 所以生产上**每一次筛选**
        # （包括市场筛选）都是 500。前端 fetch 没有错误处理，异常一抛就静默，
        # 按钮点了跟没点一样。本地 SQLite 测不出来，是 audit-svc 在生产上探到的。
        #
        # 改成按主键关联最新一行：两种数据库行为一致，且真的取到 MAX(id)。
        query = """
            SELECT w.stock_code
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            LEFT JOIN analysis_results a
              ON a.id = (SELECT MAX(r.id) FROM analysis_results r
                         WHERE r.code = w.stock_code)
            WHERE 1=1
              AND w.user_id  = :user_id
              AND w.removed_at IS NULL
        """
        params = {"user_id": user_id}
        if market:
            query += " AND s.market = :market"
            params["market"] = market
        if grade:
            if grade.upper() == GRADE_UNRATED:
                # 「NR」= 还没分析过，条件是空/NULL，不是等于字面量 'NR'
                query += " AND COALESCE(a.grade,'') = ''"
            else:
                query += " AND UPPER(COALESCE(a.grade,'')) = :grade"
                params["grade"] = grade.upper()

        from radar_app.data.core import get_conn
        try:
            with get_conn() as c:
                rows = list(c.execute(query, params))
        except Exception as e:
            # 静默 500 正是这个 bug 藏了这么久的原因
            app.logger.exception("watchlist filter failed")
            return jsonify({"error": str(e)[:200], "codes": []}), 500
        return jsonify({"codes": [r["stock_code"] for r in rows]})

    @app.route('/api/precursor-scan', methods=['POST'])
    @login_required
    def start_precursor_scan():
        user_id = session['user_id']
        job_id = create_job(user_id, 'cn', 'precursor_scan')
        t = threading.Thread(target=_precursor_worker, args=(job_id, user_id), daemon=True)
        t.start()
        return jsonify({'job_id': job_id})

    @app.route('/api/signals/watchlist')
    @login_required
    def api_watchlist_signals():
        from radar_app.data.signal_events import get_watchlist_signals
        return jsonify(get_watchlist_signals(session['user_id']))

    _precursor_scan_lock = threading.Lock()
    _precursor_scan_running = {'value': False, 'started_at': None}

    @app.route('/api/signals/scan', methods=['POST'])
    @login_required
    def api_signals_scan():
        import subprocess, os
        with _precursor_scan_lock:
            if _precursor_scan_running['value']:
                return jsonify({'status': 'running', 'started_at': _precursor_scan_running['started_at']})
            _precursor_scan_running['value'] = True
            _precursor_scan_running['started_at'] = datetime.now(CN_TZ).isoformat()

        def _run():
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                subprocess.run(
                    ['python3', 'scripts/precursor_signals.py'],
                    cwd=root, capture_output=True, timeout=600
                )
            finally:
                with _precursor_scan_lock:
                    _precursor_scan_running['value'] = False

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return jsonify({'status': 'started'})

    @app.route('/api/signals/scan/status')
    @login_required
    def api_signals_scan_status():
        with _precursor_scan_lock:
            running = _precursor_scan_running['value']
            started_at = _precursor_scan_running['started_at']
        return jsonify({'running': running, 'started_at': started_at})

    @app.route('/watchlist/performance')
    @login_required
    def performance_page():
        return render_template('performance.html', **build_performance_context(session['user_id']))
