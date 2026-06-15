"""Settings, reports, and utility routes extracted from the legacy app module."""

import os
import sqlite3
import threading

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

from radar_app.data.jobs import create_job, update_job
from radar_app.shared.auth import login_required
from radar_app.shared.i18n import clear_i18n_cache
from radar_app.system.service import (
    build_accuracy_context,
    build_report_context,
    get_settings_context,
    run_script,
    save_general_settings,
    save_push_settings,
    send_push_test,
    update_locale_preference,
)


def register_system_routes(app):
    @app.route("/report")
    @app.route("/report/<date>")
    @login_required
    def report(date=None):
        context = build_report_context(date, request.args.get("period", "daily"))
        if not context:
            flash("No report available yet.", "info")
            return redirect(url_for("index"))
        return render_template("report.html", **context)

    @app.route("/report/accuracy")
    @login_required
    def accuracy():
        return render_template("accuracy.html", **build_accuracy_context())

    @app.route("/fetch", methods=["POST"])
    @login_required
    def fetch():
        try:
            return jsonify(run_script(current_app.root_path, "stock_pipeline.py", timeout=180))
        except TimeoutError:
            return jsonify({"ok": False, "stdout": "", "stderr": "Timed out (180s)"})

    @app.route("/run-digest", methods=["POST"])
    @login_required
    def run_digest():
        mode = request.form.get("mode", "weekly")
        if mode not in ("weekly", "monthly", "quarterly"):
            flash("Invalid mode.", "warning")
            return redirect(url_for("index"))
        try:
            result = run_script(current_app.root_path, "periodic_digest.py", mode, timeout=300)
            if result["ok"]:
                flash(f"{mode.capitalize()} digest generated.", "success")
            else:
                flash(f"Error: {result['stderr'][-200:]}", "danger")
        except TimeoutError:
            flash("Timed out (5 min).", "danger")
        return redirect(url_for("index"))

    def _check_scan_token():
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        expected = os.environ.get("SCAN_TOKEN", "")
        return expected and token == expected

    @app.route("/api/trigger-pipeline", methods=["POST"])
    def trigger_pipeline():
        """GitHub Actions cron: run full daily pipeline for all watched stocks + push notifications."""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        job_id = create_job(None, "daily_pipeline", "cron_pipeline")
        app_ctx = current_app._get_current_object()

        def _run():
            update_job(job_id, "running")
            try:
                from scripts.stock_pipeline import main as run_pipeline
                run_pipeline()
                app_ctx.logger.info("[trigger-pipeline] job %s done", job_id)
            except Exception as e:
                update_job(job_id, "failed", error=str(e))
                app_ctx.logger.warning("[trigger-pipeline] job %s failed: %s", job_id, e)
                return
            try:
                from scripts.backfill_returns import backfill_predictions
                backfill_predictions()
                app_ctx.logger.info("[trigger-pipeline] backfill_predictions done")
            except Exception as e:
                app_ctx.logger.warning("[trigger-pipeline] backfill_predictions failed: %s", e)
            update_job(job_id, "done")

        threading.Thread(target=_run, daemon=False, name="gh-pipeline-trigger").start()
        return jsonify({"status": "started", "job_id": job_id}), 202

    @app.route("/api/trigger-scan", methods=["POST"])
    def trigger_scan():
        """GitHub Actions cron 调用此端点触发每日前兆扫描 + 快照提交。"""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        job_id = create_job(None, "precursor_scan", "cron_scan")
        app_ctx = current_app._get_current_object()

        def _run():
            update_job(job_id, "running")
            errors = []
            # Run precursor scan with a hard 5-min timeout so a hung scan
            # can never prevent run_daily_digest() from committing the snapshot.
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout
            try:
                from scripts.precursor_scan import run_precursor_scan
                with ThreadPoolExecutor(max_workers=1) as _ex:
                    _f = _ex.submit(run_precursor_scan)
                    try:
                        result = _f.result(timeout=300)
                        app_ctx.logger.info("[trigger-scan] precursor done: %s", result)
                    except _FuturesTimeout:
                        errors.append("precursor: timed out (300s)")
                        app_ctx.logger.warning("[trigger-scan] precursor timed out, proceeding to digest")
            except Exception as e:
                errors.append(f"precursor: {e}")
                app_ctx.logger.warning("[trigger-scan] precursor failed: %s", e)
            try:
                from scripts.daily_digest import run_daily_digest
                run_daily_digest()
                app_ctx.logger.info("[trigger-scan] daily digest done")
            except Exception as e:
                errors.append(f"digest: {e}")
                app_ctx.logger.warning("[trigger-scan] digest failed: %s", e)
            if errors:
                update_job(job_id, "failed", error="; ".join(errors))
            else:
                update_job(job_id, "done")

        threading.Thread(target=_run, daemon=False, name="gh-scan-trigger").start()
        return jsonify({"status": "started", "job_id": job_id}), 202

    @app.route("/api/trigger-backup", methods=["POST"])
    def trigger_backup():
        """Create a point-in-time SQLite backup at /data/radar.db.bak (called by GHA weekly)."""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        db_path = os.environ.get("DATABASE_URL", "").replace("sqlite:////", "/")
        if not db_path:
            db_path = "/data/radar.db"
        bak_path = db_path + ".bak"
        try:
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(bak_path)
            src.backup(dst)
            dst.close()
            src.close()
            size_kb = os.path.getsize(bak_path) // 1024
            current_app.logger.info("[backup] wrote %s (%d KB)", bak_path, size_kb)
            return jsonify({"ok": True, "path": bak_path, "size_kb": size_kb})
        except Exception as e:
            current_app.logger.error("[backup] failed: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/set-locale", methods=["POST"])
    def set_locale():
        locale = request.form.get("locale", "en")
        if locale not in ("en", "zh"):
            locale = "en"
        session["locale"] = locale
        # Auto-set home market to CN when switching to Chinese (if still on NZ default)
        current_region = session.get("region", "nz")
        if locale == "zh" and current_region == "nz":
            session["region"] = "cn"
            current_region = "cn"
        update_locale_preference(session.get("user_id"), current_region, locale)
        clear_i18n_cache()
        return redirect(request.referrer or url_for("index"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        user_id = session["user_id"]
        if request.method == "POST":
            action = request.form.get("action", "general")

            if action == "general":
                region = request.form.get("region", "nz")
                locale = request.form.get("locale", "en")
                save_general_settings(user_id, region, locale)
                session["region"] = region
                session["locale"] = locale
                clear_i18n_cache()
                flash("Settings saved.", "success")

            elif action == "push":
                notify_daily = 1 if request.form.get("notify_daily") else 0
                webhook = request.form.get("wecom_webhook", "").strip()
                save_push_settings(user_id, notify_daily, webhook)
                flash("推送设置已保存。", "success")

            elif action == "test_push":
                category, message = send_push_test(user_id)
                flash(message, category)

            return redirect(url_for("settings"))

        return render_template("settings.html", **get_settings_context(user_id))

    # ── Session status (for Next.js navbar) ──────────────────────────────────

    @app.route("/api/me")
    def api_me():
        return jsonify({
            "user_id": session.get("user_id"),
            "display_name": session.get("display_name"),
            "role": session.get("role"),
        })

    # ── Public API (no auth required) ────────────────────────────────────────

    @app.route("/api/public/feed")
    def api_public_feed():
        """Return publicly published analyses for the homepage."""
        from radar_app.data.core import get_conn
        with get_conn() as c:
            rows = c.execute("""
                SELECT ar.id, ar.code, ar.grade, ar.conclusion, ar.reasoning,
                       ar.analysis_date, ar.framework_used,
                       s.name AS stock_name, s.market
                FROM analysis_results ar
                JOIN stocks s ON s.code = ar.code
                WHERE ar.is_public = 1
                ORDER BY ar.analysis_date DESC, ar.id DESC
                LIMIT 20
            """).mappings().all()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/public/article/<code>")
    def api_public_article(code):
        """Return a single public article (full letter_html)."""
        from radar_app.data.core import get_conn
        with get_conn() as c:
            row = c.execute("""
                SELECT ar.*, s.name AS stock_name, s.market, s.industry
                FROM analysis_results ar
                JOIN stocks s ON s.code = ar.code
                WHERE ar.code = :code AND ar.is_public = 1
                ORDER BY ar.id DESC LIMIT 1
            """, {"code": code}).mappings().fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify(dict(row))

    @app.route("/api/public/poll/today")
    def api_poll_today():
        """Return today's market poll (creates one if none exists)."""
        import datetime
        from radar_app.data.core import get_conn
        today = datetime.date.today().isoformat()
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM market_polls WHERE poll_date = :d",
                {"d": today}
            ).mappings().fetchone()
            if not row:
                c.execute(
                    "INSERT INTO market_polls (poll_date, question) VALUES (:d, :q)",
                    {"d": today, "q": "大盘今天涨还是跌？"}
                )
                row = c.execute(
                    "SELECT * FROM market_polls WHERE poll_date = :d",
                    {"d": today}
                ).mappings().fetchone()
        return jsonify(dict(row))

    @app.route("/api/public/poll/vote", methods=["POST"])
    def api_poll_vote():
        """Submit a vote. Body: {direction: 'up'|'down'}. Cookie-based dedup."""
        import datetime
        from radar_app.data.core import get_conn
        today = datetime.date.today().isoformat()
        cookie_key = f"voted_{today}"
        if request.cookies.get(cookie_key):
            return jsonify({"error": "already_voted"}), 400
        data = request.get_json(silent=True) or {}
        direction = data.get("direction")
        if direction not in ("up", "down"):
            return jsonify({"error": "invalid direction"}), 400
        col = "up_votes" if direction == "up" else "down_votes"
        with get_conn() as c:
            # Ensure today's poll exists
            exists = c.execute(
                "SELECT id FROM market_polls WHERE poll_date = :d", {"d": today}
            ).fetchone()
            if not exists:
                c.execute(
                    "INSERT INTO market_polls (poll_date, question) VALUES (:d, :q)",
                    {"d": today, "q": "大盘今天涨还是跌？"}
                )
            c.execute(
                f"UPDATE market_polls SET {col} = {col} + 1 WHERE poll_date = :d",
                {"d": today}
            )
            row = c.execute(
                "SELECT up_votes, down_votes FROM market_polls WHERE poll_date = :d",
                {"d": today}
            ).mappings().fetchone()
        resp = jsonify({"up_votes": row["up_votes"], "down_votes": row["down_votes"]})
        resp.set_cookie(cookie_key, "1", max_age=86400, samesite="Lax")
        return resp

    @app.route("/api/public/city-data")
    def api_city_data():
        """Return city living cost data grouped by category (major / lifestyle).
        30-day TTL for Numbeo cities; lifestyle cities always use latest manual seed.
        """
        import threading
        from scripts.fetch_city_costs import _ensure_table, get_all_cities, is_stale, refresh_all

        _ensure_table()
        cities = get_all_cities()

        major_stale = [c for c in cities if c.get("city_category") == "major"
                       and is_stale(c.get("fetched_at", ""), days=30)]
        needs_refresh = len(cities) == 0 or len(major_stale) > 0

        if len(cities) == 0:
            cities = refresh_all()
        elif needs_refresh:
            threading.Thread(target=refresh_all, daemon=True).start()

        # Determine display year (most recent report_year in DB)
        years = [c["report_year"] for c in cities if c.get("report_year")]
        report_year = max(years) if years else 2025

        return jsonify({
            "cities": cities,
            "report_year": report_year,
        })
