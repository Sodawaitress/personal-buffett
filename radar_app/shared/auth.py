"""Shared auth decorators and guards."""

from functools import wraps

from flask import redirect, session, url_for


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


def admin_required():
    return session.get("role") == "admin"
