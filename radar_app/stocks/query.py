"""Stock detail data access helpers."""

import db
from radar_app.shared.jobs import get_recent_pending_job


def get_pending_job(code):
    return get_recent_pending_job(code)


def get_stock_page_bundle(code, user_id):
    code = code.upper()
    stock = db.get_stock(code)
    if not stock:
        return None

    market = stock.get("market", "us")
    return {
        "code": code,
        "stock": stock,
        "market": market,
        "price": db.get_latest_price(code),
        "news": db.get_stock_news(code, days=7),
        "analysis": db.get_latest_analysis(code, period="daily"),
        "history": db.get_analysis_history(code, period="daily", limit=20),
        "prices": db.get_price_history(code, days=30),
        "fund_flow": db.get_fund_flow(code) if market == "cn" else {},
        "ff_hist": db.get_fund_flow_history(code, days=60) if market == "cn" else [],
        "north_bound": db.get_north_bound() if market == "cn" else {},
        "fund": db.get_fundamentals(code),
        "pending_job": get_pending_job(code),
        "in_watchlist": any(row.get("stock_code") == code for row in db.get_user_watchlist(user_id)),
        "meta": db.get_stock_meta(code),
        "events": db.get_stock_events(code),
    }


def get_latest_daily_analysis(code):
    return db.get_latest_analysis(code, period="daily")


def get_job(job_id):
    return db.get_job(job_id)


def get_job_analysis(code):
    return db.get_latest_analysis(code)
