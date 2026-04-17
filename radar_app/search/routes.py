"""Search-related routes extracted from the legacy app module."""

from flask import jsonify, request

from radar_app.shared.auth import login_required
from radar_app.search.service import search_payload


def register_search_routes(app):
    @app.route('/api/search')
    @login_required
    def api_search():
        """股票模糊搜索：AKShare(A股) + yfinance(其他)"""
        q = request.args.get('q', '').strip()
        return search_payload(q)
