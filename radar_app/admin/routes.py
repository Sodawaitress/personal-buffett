"""Admin routes extracted from the legacy app module."""

from flask import flash, redirect, render_template, request, session, url_for

from radar_app.admin.service import (
    get_admin_user_context,
    list_users_with_push,
    save_admin_push_settings,
    send_admin_push_test,
)
from radar_app.shared.auth import admin_required, login_required


def register_admin_routes(app):
    @app.route("/admin/users")
    @login_required
    def admin_users():
        if not admin_required():
            return "Forbidden", 403
        return render_template("admin_users.html", users=list_users_with_push())

    @app.route("/admin/users/<int:target_uid>", methods=["GET", "POST"])
    @login_required
    def admin_user_detail(target_uid):
        if not admin_required():
            return "Forbidden", 403

        context = get_admin_user_context(target_uid)
        if not context:
            return "User not found", 404

        if request.method == "POST":
            action = request.form.get("action")

            if action == "push":
                notify_daily = 1 if request.form.get("notify_daily") else 0
                wecom_key = request.form.get("wecom_webhook", "").strip()
                save_admin_push_settings(target_uid, notify_daily, wecom_key)
                flash(f"已更新 {context['target']['email']} 的推送设置。", "success")

            elif action == "test_push":
                category, message = send_admin_push_test(target_uid)
                flash(message, category)

            return redirect(url_for("admin_user_detail", target_uid=target_uid))

        return render_template("admin_user_detail.html", **context)
