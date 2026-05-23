"""Dashboard and brief routes extracted from the legacy app module."""

import threading
from datetime import datetime, timedelta, timezone

from flask import jsonify, render_template, session

from radar_app.data.core import get_conn
from radar_app.data.stocks import get_user_watchlist
from radar_app.shared.auth import login_required
from radar_app.dashboard.service import build_brief_context, build_dashboard_context
from radar_app.shared.startup import ensure_db_ready

CN_TZ = timezone(timedelta(hours=8))
_home_refresh_state = {"running": False, "started_at": None, "step": ""}


def _precursor_age_hours(user_id: int) -> float:
    """返回该用户自选 A 股前兆缓存的最老更新时间（小时）。"""
    try:
        stocks = get_user_watchlist(user_id, status=None)
        codes = [s["stock_code"] for s in stocks
                 if s.get("market") == "cn" and s.get("status") in ("holding", "watching")]
        if not codes:
            return 0
        with get_conn() as c:
            placeholders = ",".join("?" * len(codes))
            row = c.execute(
                f"SELECT MIN(fetched_at) as oldest FROM stock_precursor_cache WHERE code IN ({placeholders})",
                codes,
            ).fetchone()
        if not row or not row["oldest"]:
            return 999
        oldest = datetime.fromisoformat(row["oldest"].replace(" ", "T"))
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=CN_TZ)
        return (datetime.now(CN_TZ) - oldest).total_seconds() / 3600
    except Exception:
        return 999


def register_dashboard_routes(app):
    @app.route("/")
    @login_required
    def index():
        ensure_db_ready()
        locale = session.get("locale", "en")
        region = session.get("region") or ("cn" if locale == "zh" else "nz")
        return render_template("index.html", **build_dashboard_context(session["user_id"], region, locale))

    @app.route("/brief")
    @login_required
    def brief_page():
        ensure_db_ready()
        return render_template("brief.html", **build_brief_context(session["user_id"]))

    @app.route("/api/home/refresh", methods=["POST"])
    @login_required
    def api_home_refresh():
        """快速拉取价格 + 资金流向。若前兆数据 >20h 则同时触发前兆扫描。"""
        import subprocess, os
        if _home_refresh_state["running"]:
            return jsonify({"status": "running", "step": _home_refresh_state["step"]})

        user_id = session["user_id"]
        precursor_stale = _precursor_age_hours(user_id) > 20

        def _run():
            _home_refresh_state["running"] = True
            _home_refresh_state["started_at"] = datetime.now(CN_TZ).isoformat()
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            try:
                # 快速数据：用现有的价格/资金流 pipeline
                _home_refresh_state["step"] = "price"
                subprocess.run(
                    ["python3", "scripts/fetch_home_fast.py"],
                    cwd=root, capture_output=True, timeout=120
                )
                # 前兆数据（如果过期）
                if precursor_stale:
                    _home_refresh_state["step"] = "precursor"
                    subprocess.run(
                        ["python3", "scripts/precursor_signals.py"],
                        cwd=root, capture_output=True, timeout=600
                    )
            finally:
                _home_refresh_state["running"] = False
                _home_refresh_state["step"] = "done"

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"status": "started", "precursor_stale": precursor_stale})

    @app.route("/api/home/refresh/status")
    @login_required
    def api_home_refresh_status():
        user_id = session["user_id"]
        age_h = _precursor_age_hours(user_id)
        if age_h < 6:
            precursor_label = "今日"
        elif age_h < 30:
            precursor_label = f"{int(age_h)}小时前"
        else:
            precursor_label = f"{int(age_h / 24)}天前"
        return jsonify({
            "running":         _home_refresh_state["running"],
            "step":            _home_refresh_state["step"],
            "precursor_age_h": round(age_h, 1),
            "precursor_label": precursor_label,
        })
