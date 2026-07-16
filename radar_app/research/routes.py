"""行业分析专栏路由（US-127）。"""

from flask import abort, render_template, request

from radar_app.shared.auth import login_required
from radar_app.research.articles import get_article, list_articles


def register_research_routes(app):
    @app.route("/research")
    @login_required
    def research_archive():
        return render_template("research_archive.html", articles=list_articles())

    @app.route("/research/<slug>")
    @login_required
    def research_article(slug):
        article = get_article(slug)
        if not article:
            abort(404)
        return render_template(article["template"], embed=bool(request.args.get("embed")))
