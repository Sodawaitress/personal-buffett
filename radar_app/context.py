"""Flask context processor registration."""

import urllib.request
import json

from flask import request, session

from radar_app.shared.i18n import load_strings
from radar_app.shared.market import MARKET_CURRENCY

# 國家代碼 → (locale, region)
_COUNTRY_MAP = {
    "CN": ("zh", "cn"),
    "HK": ("zh", "hk"),
    "TW": ("zh", "tw"),
    "MO": ("zh", "cn"),
}

def _detect_locale_by_ip(ip: str):
    """Query ip-api.com to get country, return (locale, region). Falls back to ('en','nz')."""
    try:
        url = f"http://ip-api.com/json/{ip}?fields=countryCode,regionName"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        country = data.get("countryCode", "")
        return _COUNTRY_MAP.get(country, ("en", "nz"))
    except Exception:
        return ("en", "nz")


def _get_real_ip() -> str:
    """Get real client IP, respecting reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def register_context_processors(app):
    @app.before_request
    def auto_detect_locale():
        """Detect locale from IP geolocation on the very first visit."""
        if "locale" not in session:
            ip = _get_real_ip()
            locale, region = _detect_locale_by_ip(ip)
            session["locale"] = locale
            if "region" not in session:
                session["region"] = region

    @app.context_processor
    def inject_i18n():
        locale = session.get("locale", "en")
        return {
            "t": load_strings(locale),
            "locale": locale,
            "user_region": session.get("region", "nz"),
            "market_currency": MARKET_CURRENCY,
        }
