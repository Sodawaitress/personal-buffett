"""Authentication service helpers."""

import db
from flask import session
from radar_app.shared.startup import ensure_db_ready


def validate_password(password):
    import re

    if len(password) < 8:
        return "At least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Add an uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Add a lowercase letter."
    if not re.search(r"\d", password):
        return "Add a number."
    return None


def set_user_session(user):
    session["user_id"] = user["id"]
    session["display_name"] = user.get("display_name") or user.get("email", "").split("@")[0]
    session["avatar_url"] = user.get("avatar_url", "")
    session["locale"] = user.get("locale", "en")
    session["region"] = user.get("region", "nz")
    session["role"] = user.get("role", "member")


def complete_google_login(google):
    token = google.authorize_access_token()
    userinfo = token.get("userinfo") or google.userinfo()
    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email.split("@")[0])
    avatar = userinfo.get("picture", "")

    ensure_db_ready(run_migrations=False)
    user = db.get_or_create_oauth_user("google", google_id, email, name, avatar)
    set_user_session(
        {
            **user,
            "display_name": user.get("display_name") or name,
            "avatar_url": user.get("avatar_url") or avatar,
        }
    )


def authenticate_login(form, bcrypt):
    errors = {}
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    user = db.get_user_by_email(email)

    if not user or not user.get("password_hash"):
        errors["email"] = "No account found with this email."
        return errors
    if not bcrypt.check_password_hash(user["password_hash"], password):
        errors["password"] = "Incorrect password."
        return errors

    set_user_session(user)
    return errors


def register_email_user(form, bcrypt):
    errors = {}
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")

    if not email or "@" not in email:
        errors["email"] = "Enter a valid email address."
    elif db.user_exists(email=email):
        errors["email"] = "An account with this email already exists."

    password_error = validate_password(password)
    if password_error:
        errors["password"] = password_error
    elif password != confirm_password:
        errors["confirm_password"] = "Passwords don't match."

    if errors:
        return errors

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    db.create_user(
        email=email,
        password_hash=password_hash,
        display_name=email.split("@")[0],
    )
    user = db.get_user_by_email(email)
    set_user_session(user)
    return errors
