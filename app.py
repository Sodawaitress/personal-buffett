#!/usr/bin/env python3
"""Personal Buffett · Flask app with Google OAuth + email/password"""

import sys, os, re, subprocess
sys.path.insert(0, os.path.dirname(__file__))

import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_bcrypt import Bcrypt
from authlib.integrations.flask_client import OAuth
import db
from scripts.config import CN_TZ, BUFFETT_PROFILES

app    = Flask(__name__)
bcrypt = Bcrypt(app)
oauth  = OAuth(app)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "personal-buffett-2024-xK9m")

# ── Google OAuth ──────────────────────────────────────
# Fill in after getting credentials from Google Cloud Console
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

google = oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def _validate_password(pw):
    if len(pw) < 8:              return "At least 8 characters."
    if not re.search(r"[A-Z]", pw): return "Add an uppercase letter."
    if not re.search(r"[a-z]", pw): return "Add a lowercase letter."
    if not re.search(r"\d", pw):    return "Add a number."
    return None


# ── Google OAuth routes ───────────────────────────────
@app.route("/auth/google")
def google_login():
    redirect_uri = url_for("google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def google_callback():
    try:
        token    = google.authorize_access_token()
        userinfo = token.get("userinfo") or google.userinfo()
        g_id     = userinfo["sub"]
        email    = userinfo["email"]
        name     = userinfo.get("name", email.split("@")[0])
        avatar   = userinfo.get("picture", "")

        db.init_db()
        user = db.get_or_create_google_user(g_id, email, name, avatar)
        session["user_id"]      = user["id"]
        session["display_name"] = user.get("display_name") or name
        session["avatar_url"]   = user.get("avatar_url") or avatar
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Google sign-in failed: {e}", "danger")
        return redirect(url_for("login"))


# ── Email auth ────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    errors = {}
    form   = {}

    if request.method == "POST":
        form  = request.form.to_dict()
        email = form.get("email", "").strip().lower()
        pw    = form.get("password", "")
        user  = db.get_user_by_email(email)
        if not user or not user.get("password_hash"):
            errors["email"] = "No account found with this email."
        elif not bcrypt.check_password_hash(user["password_hash"], pw):
            errors["password"] = "Incorrect password."
        else:
            _set_session(user)
            return redirect(url_for("index"))

    return render_template("login.html", errors=errors, form=form,
                           google_enabled=bool(GOOGLE_CLIENT_ID))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    errors = {}
    form   = {}

    if request.method == "POST":
        form  = request.form.to_dict()
        email = form.get("email", "").strip().lower()
        pw    = form.get("password", "")
        pw2   = form.get("confirm_password", "")

        if not email or "@" not in email:
            errors["email"] = "Enter a valid email address."
        elif db.user_exists(email=email):
            errors["email"] = "An account with this email already exists."

        pw_err = _validate_password(pw)
        if pw_err:             errors["password"] = pw_err
        elif pw != pw2:        errors["confirm_password"] = "Passwords don't match."

        if not errors:
            pw_hash = bcrypt.generate_password_hash(pw).decode("utf-8")
            db.create_user(email=email, password_hash=pw_hash,
                           display_name=email.split("@")[0])
            user = db.get_user_by_email(email)
            _set_session(user)
            return redirect(url_for("index"))

    return render_template("register.html", errors=errors, form=form,
                           google_enabled=bool(GOOGLE_CLIENT_ID))


def _set_session(user):
    session["user_id"]      = user["id"]
    session["display_name"] = user.get("display_name") or user.get("email","").split("@")[0]
    session["avatar_url"]   = user.get("avatar_url", "")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────
@app.route("/")
@login_required
def index():
    db.init_db()
    watchlist = db.get_user_watchlist(session["user_id"])
    quote_map = {q["code"]: q for q in db.get_quotes()}
    reports   = db.list_reports(limit=10)
    latest    = db.get_report()

    stocks = []
    for row in watchlist:
        code    = row["code"]
        q       = quote_map.get(code, {})
        profile = BUFFETT_PROFILES.get(code, {})
        ff      = db.get_fund_flow(code)
        stocks.append({
            "code":        code,
            "name":        row["name"],
            "description": row["description"],
            "price":       q.get("price"),
            "change_pct":  q.get("change_pct"),
            "amount":      q.get("amount"),
            "grade":       profile.get("grade", "—"),
            "grade_emoji": profile.get("grade_emoji", ""),
            "moat":        profile.get("moat", "—"),
            "main_net":    ff.get("main_net") if ff else None,
        })

    return render_template("index.html",
        stocks=stocks, reports=reports, latest_report=latest,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Watchlist ─────────────────────────────────────────
@app.route("/add", methods=["POST"])
@login_required
def add_stock():
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    desc = request.form.get("desc", "").strip()
    if not code or not name:
        flash("Stock code and name are required.", "warning")
    else:
        db.add_user_stock(session["user_id"], code, name, desc)
        flash(f"{name} ({code}) added.", "success")
    return redirect(url_for("index"))


@app.route("/remove/<code>", methods=["POST"])
@login_required
def remove_stock(code):
    db.remove_user_stock(session["user_id"], code)
    return redirect(url_for("index"))


# ── Reports ───────────────────────────────────────────
@app.route("/report")
@app.route("/report/<date>")
@login_required
def report(date=None):
    row = db.get_report(date)
    if not row:
        flash("No report available yet.", "info")
        return redirect(url_for("index"))
    return render_template("report.html",
        report=row, reports=db.list_reports(limit=30),
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Fetch ─────────────────────────────────────────────
@app.route("/fetch", methods=["POST"])
@login_required
def fetch():
    script = os.path.join(os.path.dirname(__file__), "scripts", "stock_pipeline.py")
    try:
        result = subprocess.run([sys.executable, script],
            capture_output=True, text=True, timeout=180)
        return jsonify({"ok": result.returncode == 0,
                        "stdout": result.stdout[-3000:],
                        "stderr": result.stderr[-500:]})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "stdout": "", "stderr": "Timed out (180s)"})


# ── API ───────────────────────────────────────────────
@app.route("/api/news/<code>")
@login_required
def api_news(code):
    return jsonify(db.get_news(code, days=3))


if __name__ == "__main__":
    db.init_db()
    print("🚀 Personal Buffett → http://127.0.0.1:5001")
    app.run(debug=True, port=5001)
