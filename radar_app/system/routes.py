"""Settings, reports, and utility routes extracted from the legacy app module."""

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

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
