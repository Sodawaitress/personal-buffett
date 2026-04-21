"""Dashboard data assembly helpers."""

from datetime import datetime

from radar_app.dashboard.presenter import (
    now_label,
    present_brief_stock,
    present_index_stock,
    present_intl_news,
    present_portfolio_brief,
)
from radar_app.dashboard.query import (
    get_fomc_news_items,
    get_intl_stock_news,
    get_local_news,
    get_market_snapshot,
    get_pending_job,
    get_portfolio_brief,
    get_reports_bundle,
    get_stock_snapshot,
    list_active_watchlist,
)
from radar_app.shared.runtime import CN_TZ


def _build_index_stocks(user_id):
    stocks = []
    for row in list_active_watchlist(user_id):
        code = row.get("stock_code") or row.get("code")
        market = row.get("market")
        stocks.append(present_index_stock(row, get_stock_snapshot(code, market), get_pending_job(code)))
    return stocks


def _build_brief_stocks(user_id, locale="en"):
    stocks = []
    for row in list_active_watchlist(user_id):
        code = row.get("stock_code") or row.get("code")
        stocks.append(present_brief_stock(row, get_stock_snapshot(code, row.get("market")), locale))
    return stocks


def build_dashboard_context(user_id, region, locale="en"):
    stocks = _build_index_stocks(user_id)
    market = get_market_snapshot()
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    intl_news = get_intl_stock_news(stocks)
    intl_news.extend(get_fomc_news_items(limit=2))
    return {
        "stocks": stocks,
        "local_stocks": [stock for stock in stocks if stock["market"] == region],
        "intl_stocks": [stock for stock in stocks if stock["market"] != region],
        "local_news": get_local_news("cn" if locale == "zh" else "nz"),
        "intl_news": present_intl_news(intl_news, market),
        "market": market,
        "portfolio_brief": present_portfolio_brief(get_portfolio_brief(user_id, date=today)),
        "now": now_label(),
        **get_reports_bundle(),
    }


def build_brief_context(user_id, locale="en"):
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    market_snapshot = get_market_snapshot()
    return {
        "stocks": _build_brief_stocks(user_id, locale),
        "portfolio_brief": present_portfolio_brief(get_portfolio_brief(user_id, date=today)),
        "market": market_snapshot,
        "now": now_label(),
    }
