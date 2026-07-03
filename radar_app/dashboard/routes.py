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


def _refresh_state() -> dict:
    """Query pipeline_jobs for a recent home_refresh run — works across gunicorn workers."""
    try:
        with get_conn() as c:
            row = c.execute(
                """SELECT status, log, started_at FROM pipeline_jobs
                   WHERE job_type='home_refresh'
                   ORDER BY id DESC LIMIT 1"""
            ).fetchone()
        if row and row["status"] == "running":
            started = row["started_at"] or ""
            # treat stale locks (>15 min) as done
            try:
                age = (datetime.now(CN_TZ) - datetime.fromisoformat(started).replace(tzinfo=CN_TZ)).total_seconds()
                if age > 900:
                    return {"running": False, "step": "done"}
            except Exception:
                pass
            return {"running": True, "step": row["log"] or ""}
    except Exception:
        pass
    return {"running": False, "step": "done"}


def _precursor_age_hours(user_id: int) -> float:
    """返回该用户自选 A 股前兆缓存的最老更新时间（小时）。"""
    try:
        stocks = get_user_watchlist(user_id, status=None)
        codes = [s["stock_code"] for s in stocks
                 if s.get("market") == "cn" and s.get("status") in ("holding", "watching")]
        if not codes:
            return 0
        with get_conn() as c:
            params = {f"c{i}": code for i, code in enumerate(codes)}
            placeholders = ",".join(f":{k}" for k in params)
            row = c.execute(
                f"SELECT MAX(fetched_at) as oldest FROM stock_precursor_cache WHERE code IN ({placeholders})",
                params,
            ).fetchone()
        if not row or not row["oldest"]:
            return 999
        oldest = row["oldest"]
        if isinstance(oldest, str):
            oldest = datetime.fromisoformat(oldest.replace(" ", "T"))
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
        state = _refresh_state()
        if state["running"]:
            return jsonify({"status": "running", "step": state["step"]})

        user_id = session["user_id"]
        precursor_stale = _precursor_age_hours(user_id) > 20

        def _run():
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            started = datetime.now(CN_TZ).isoformat()
            try:
                with get_conn() as c:
                    c.execute(
                        "INSERT INTO pipeline_jobs (job_type, status, log, started_at) VALUES ('home_refresh','running','price',:ts)",
                        {"ts": started}
                    )
                    job_id = c.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
            except Exception:
                job_id = None

            def _update(step):
                if job_id:
                    try:
                        with get_conn() as c:
                            c.execute("UPDATE pipeline_jobs SET log=:s WHERE id=:id", {"s": step, "id": job_id})
                    except Exception:
                        pass

            try:
                subprocess.run(["python3", "scripts/fetch_home_fast.py"], cwd=root, capture_output=True, timeout=120)
                if precursor_stale:
                    _update("precursor")
                    subprocess.run(["python3", "scripts/precursor_signals.py"], cwd=root, capture_output=True, timeout=600)
            finally:
                if job_id:
                    try:
                        with get_conn() as c:
                            c.execute(
                                "UPDATE pipeline_jobs SET status='done', log='done', finished_at=:ts WHERE id=:id",
                                {"ts": datetime.now(CN_TZ).isoformat(), "id": job_id}
                            )
                    except Exception:
                        pass

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"status": "started", "precursor_stale": precursor_stale})

    @app.route("/api/home/refresh/status")
    @login_required
    def api_home_refresh_status():
        user_id = session["user_id"]
        state = _refresh_state()
        age_h = _precursor_age_hours(user_id)
        if age_h < 6:
            precursor_label = "今日"
        elif age_h < 30:
            precursor_label = f"{int(age_h)}小时前"
        else:
            precursor_label = f"{int(age_h / 24)}天前"
        return jsonify({
            "running":         state["running"],
            "step":            state["step"],
            "precursor_age_h": round(age_h, 1),
            "precursor_label": precursor_label,
        })
