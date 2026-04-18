"""Flask context processor registration."""

from flask import request, session

from radar_app.shared.i18n import load_strings
from radar_app.shared.market import MARKET_CURRENCY


def register_context_processors(app):
    @app.before_request
    def auto_detect_locale():
        """Infer locale from Accept-Language header on the very first visit."""
        if "locale" not in session:
            accept = request.headers.get("Accept-Language", "")
            is_zh = any(
                seg.strip().split(";")[0].strip().lower().startswith("zh")
                for seg in accept.split(",")
            )
            if is_zh:
                session["locale"] = "zh"
                if "region" not in session:
                    session["region"] = "cn"

    @app.context_processor
    def inject_i18n():
        locale = session.get("locale", "en")
        return {
            "t": load_strings(locale),
            "locale": locale,
            "user_region": session.get("region", "nz"),
            "market_currency": MARKET_CURRENCY,
        }
