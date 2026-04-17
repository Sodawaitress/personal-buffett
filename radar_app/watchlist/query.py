"""Watchlist data access helpers."""

import db
from radar_app.shared.jobs import get_recent_pending_job


def get_pending_job(code):
    return get_recent_pending_job(code)


def list_watchlist_rows(user_id):
    return db.get_user_watchlist(user_id)


def get_watchlist_snapshot(code, market):
    return {
        "price": db.get_latest_price(code),
        "analysis": db.get_latest_analysis(code, period="daily"),
        "fund": db.get_fundamentals(code) if market == "cn" else {},
        "pending_job": get_pending_job(code),
    }


def get_active_notifications(user_id):
    return db.get_active_notifications(user_id)


def get_performance_rows(user_id):
    return db.get_performance_data(user_id)


def get_quote_map():
    return {quote["code"]: quote for quote in db.get_quotes()}
