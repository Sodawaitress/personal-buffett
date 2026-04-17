"""Portfolio-related routes extracted from the legacy app module."""

from flask import jsonify, session

from radar_app.shared.auth import login_required
from radar_app.portfolio.service import generate_brief_for_user


def register_portfolio_routes(app):
    @app.route('/api/generate-brief', methods=['POST'])
    @login_required
    def api_generate_brief():
        """手动触发组合日报 LLM 合成，存入 portfolio_analysis 表。"""
        try:
            return jsonify(generate_brief_for_user(session["user_id"], session.get("locale", "zh")))
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
