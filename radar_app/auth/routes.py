"""Authentication helpers and routes extracted from the legacy app module."""

import os
import re

from flask import flash, redirect, render_template, request, session, url_for

from radar_app.auth.service import (
    authenticate_login,
    complete_google_login,
    register_email_user,
)


def register_auth_routes(app, bcrypt, oauth):
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    google = oauth.register(
        name="google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    @app.route("/auth/google")
    def google_login():
        redirect_uri = url_for("google_callback", _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route("/auth/google/callback")
    def google_callback():
        try:
            complete_google_login(google)
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Google sign-in failed: {e}", "danger")
            return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "user_id" in session:
            return redirect(url_for("index"))

        errors = {}
        form = {}

        if request.method == "POST":
            form = request.form.to_dict()
            errors = authenticate_login(form, bcrypt)
            if not errors:
                return redirect(url_for("index"))

        return render_template(
            "login.html",
            errors=errors,
            form=form,
            google_enabled=bool(google_client_id),
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if "user_id" in session:
            return redirect(url_for("index"))

        errors = {}
        form = {}

        if request.method == "POST":
            form = request.form.to_dict()
            errors = register_email_user(form, bcrypt)
            if not errors:
                return redirect(url_for("index"))

        return render_template(
            "register.html",
            errors=errors,
            form=form,
            google_enabled=bool(google_client_id),
        )

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/demo")
    def demo_login():
        """One-click demo access — no registration required."""
        from radar_app.auth.demo import ensure_demo_user
        demo_user = ensure_demo_user()
        session.clear()
        session["user_id"]      = demo_user["id"]
        session["display_name"] = "Demo"
        session["avatar_url"]   = ""
        session["locale"]       = "en"
        session["region"]       = "nz"
        session["role"]         = "member"
        session["is_demo"]      = True
        next_code = request.args.get("next", "")
        if next_code and re.match(r'^[\w.\-]+$', next_code):
            return redirect(f"/stock/{next_code}")
        return redirect(url_for("watchlist_page"))
