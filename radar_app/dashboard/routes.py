"""Dashboard and brief routes extracted from the legacy app module."""

from flask import render_template, session

from radar_app.shared.auth import login_required
from radar_app.dashboard.service import build_brief_context, build_dashboard_context
from radar_app.shared.startup import ensure_db_ready


def register_dashboard_routes(app):
    @app.route("/")
    @login_required
    def index():
        ensure_db_ready()
        # Derive region from locale if not explicitly set (zh → cn, else nz)
        region = session.get("region") or ("cn" if session.get("locale") == "zh" else "nz")
        return render_template("index.html", **build_dashboard_context(session["user_id"], region))

    @app.route("/brief")
    @login_required
    def brief_page():
        ensure_db_ready()
        return render_template("brief.html", **build_brief_context(session["user_id"]))
