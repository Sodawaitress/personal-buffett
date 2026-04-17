"""Public page service helpers."""

from radar_app.legacy.market_data import (
    NZ_PROFILES,
    NZ_SECTORS,
    fetch_all_nz_quotes,
    fetch_nz_market_news,
    fetch_nzx50,
)


def build_home_context(logged_in):
    nzx50 = fetch_nzx50()
    quotes = fetch_all_nz_quotes()
    news = fetch_nz_market_news()
    movers = sorted(quotes.values(), key=lambda item: abs(item.get("change", 0)), reverse=True)[:4]
    picks = [ticker for ticker, profile in NZ_PROFILES.items() if profile["grade"] == "A"]
    return {
        "nzx50": nzx50,
        "movers": movers,
        "news": news,
        "sectors": NZ_SECTORS,
        "picks": picks,
        "pick_quotes": {ticker: quotes.get(ticker, {}) for ticker in picks},
        "profiles": NZ_PROFILES,
        "logged_in": logged_in,
    }
