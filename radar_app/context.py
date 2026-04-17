"""Flask context processor registration."""

from flask import session

from radar_app.shared.i18n import load_strings
from radar_app.shared.market import MARKET_CURRENCY


def register_context_processors(app):
    @app.context_processor
    def inject_i18n():
        locale = session.get("locale", "en")
        return {
            "t": load_strings(locale),
            "locale": locale,
            "user_region": session.get("region", "nz"),
            "market_currency": MARKET_CURRENCY,
        }
