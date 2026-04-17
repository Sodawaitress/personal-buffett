"""Watchlist service orchestration."""

from datetime import datetime

import db
from radar_app.legacy.pipeline import classify_stock_code, start_pipeline_job
from radar_app.shared.market import detect_market
from radar_app.shared.runtime import CN_TZ
from radar_app.watchlist.presenter import calc_performance_stats, present_performance_row, present_watchlist_stock
from radar_app.watchlist.query import (
    get_active_notifications,
    get_performance_rows,
    get_quote_map,
    get_watchlist_snapshot,
    list_watchlist_rows,
)


def build_watchlist_context(user_id):
    stocks = []
    for row in list_watchlist_rows(user_id):
        code = row.get("stock_code") or row.get("code")
        market = row.get("market") or detect_market(code)
        stocks.append(present_watchlist_stock(row, get_watchlist_snapshot(code, market)))

    return {
        "stocks": stocks,
        "holding": [stock for stock in stocks if stock["status"] == "holding"],
        "watching": [stock for stock in stocks if stock["status"] == "watching"],
        "sold": [stock for stock in stocks if stock["status"] == "sold"],
        "notifications": get_active_notifications(user_id),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "now_date": datetime.now(CN_TZ).strftime("%Y-%m-%d"),
    }


def add_stock_and_start_analysis(user_id, code, name, market, notes):
    if not market:
        market = detect_market(code)
    if market == 'nz' and not code.endswith('.NZ'):
        code += '.NZ'

    db.add_user_stock(user_id, code, name, market, notes=notes)

    try:
        classify_stock_code(code)
    except Exception:
        pass

    start_pipeline_job(user_id, code, market)
    return code, market


def update_watchlist_stock_status(user_id, code, data):
    status = data.get('status')
    if status not in ('watching', 'holding', 'sold'):
        return None

    entry_grade = None
    if status == 'holding':
        analysis = db.get_latest_analysis(code, period='daily')
        if analysis:
            entry_grade = analysis.get('grade')

    db.update_stock_status(
        user_id,
        code,
        status,
        buy_date=data.get('buy_date'),
        buy_price=float(data['buy_price']) if data.get('buy_price') else None,
        sell_date=data.get('sell_date'),
        sell_price=float(data['sell_price']) if data.get('sell_price') else None,
        entry_grade=entry_grade,
    )
    return {'ok': True, 'entry_grade': entry_grade}


def build_performance_context(user_id):
    quote_map = get_quote_map()
    today = datetime.now(CN_TZ).date()

    holdings = []
    sold = []
    for row in get_performance_rows(user_id):
        perf = present_performance_row(row, quote_map.get(row["code"], {}), today)
        if row["status"] == "holding":
            holdings.append(perf)
        else:
            sold.append(perf)

    return {
        "holdings": holdings,
        "sold": sold,
        "stats": calc_performance_stats(holdings + sold),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }
