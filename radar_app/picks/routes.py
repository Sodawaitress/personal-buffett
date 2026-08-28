"""今日五选的路由（US-196）。"""
from flask import render_template

from radar_app.shared.auth import login_required


def register_picks_routes(app):
    @app.route("/picks")
    @login_required
    def picks_today():
        from radar_app.picks.service import archive, build
        return render_template("picks.html", doc=build(), archive=archive())
