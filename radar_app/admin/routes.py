"""Admin routes extracted from the legacy app module."""

import os

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.admin.service import (
    get_admin_user_context,
    list_users_with_push,
    save_admin_push_settings,
    send_admin_push_test,
)
from radar_app.shared.auth import admin_required, login_required


def register_admin_routes(app):
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        users = list_users_with_push()
        questions_count = db.count_recent_questions(hours=24)
        return render_template("admin_dashboard.html", users=users, questions_count=questions_count)

    @app.route("/admin/users")
    @admin_required
    def admin_users():
        return render_template("admin_users.html", users=list_users_with_push())

    @app.route("/admin/users/<int:target_uid>", methods=["GET", "POST"])
    @admin_required
    def admin_user_detail(target_uid):

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

    @app.route("/api/ask", methods=["POST"])
    @login_required
    def api_ask():
        data     = request.get_json() or {}
        question = (data.get("question") or "").strip()[:300]
        if not question:
            return jsonify({"error": "empty question"}), 400

        locale = session.get("locale", "zh")
        if locale == "zh":
            sys_prompt = (
                "你是「私人巴菲特」的投资助手，帮助普通投资者理解股票数据和投资概念。"
                "用简洁口语化的中文回答，不超过150字，不使用 Markdown 格式符号。"
            )
        else:
            sys_prompt = (
                "You are the investment assistant for Personal Buffett, helping everyday investors "
                "understand stock data and investing concepts. Reply in plain conversational English, "
                "under 120 words, no Markdown formatting."
            )

        try:
            import requests as _req
            groq_key = os.environ.get("GROQ_API_KEY", "")
            resp = _req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user",   "content": question},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.4,
                },
                timeout=20,
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            answer = "暂时无法回答，稍后再试。" if locale == "zh" else "Couldn't answer right now — please try again shortly."

        db.save_question(session["user_id"], question, answer)
        return jsonify({"answer": answer})

    @app.route("/admin/questions")
    @admin_required
    def admin_questions():
        questions = db.list_questions(limit=200)
        recent_n  = db.count_recent_questions(hours=24)
        return render_template("admin_questions.html",
                               questions=questions, recent_n=recent_n)
