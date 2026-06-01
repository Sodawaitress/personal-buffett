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
            try:
                from scripts.precursor_scan import run_precursor_scan
                result = run_precursor_scan()
                app_ctx.logger.info("[trigger-scan] precursor done: %s", result)
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
