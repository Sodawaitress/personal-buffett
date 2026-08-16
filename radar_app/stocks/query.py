"""Stock detail data access helpers."""

import db
from radar_app.data.stocks import (
    get_analyst_consensus,
    get_industry_signal,
    get_price_52week,
    get_watchlist_entry,
)
from radar_app.shared.jobs import get_recent_pending_job


def get_pending_job(code):
    return get_recent_pending_job(code)


def get_stock_page_bundle(code, user_id):
    code = code.upper()
    stock = db.get_stock(code)
    if not stock:
        return None

    market = stock.get("market", "us")
    meta = db.get_stock_meta(code)
    watchlist_entry = get_watchlist_entry(user_id, code)
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
        "in_watchlist": watchlist_entry is not None,
        "meta": meta,
        "events": db.get_stock_events(code),
        "material_events": _material_events(code),
        "watchlist_entry": watchlist_entry,
        "price_52w": get_price_52week(code),
        "analyst_consensus": get_analyst_consensus(code),
        "industry_signal":   _get_industry_signal_for_stock(code, market, meta),
    }


def _material_events(code: str):
    """US-118：取 news_material 事件，解析 detail_json，按材料度取前 3。"""
    import json
    out = []
    for e in db.get_stock_events(code) or []:
        if e.get("source") != "news_material":
            continue
        try:
            d = json.loads(e.get("detail_json") or "{}")
        except Exception:
            d = {}
        d["event_date"] = e.get("event_date")
        out.append(d)
    out.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return out[:3]


def _get_industry_signal_for_stock(code: str, market: str, meta: dict):
    """US-158：改为按个股真实行业查，不再走 company_type。

    原来用 company_type（商业形态）当行业：茅台和长江电力都是 mature_value，
    映射到同一个板块没有意义；而且映射表只覆盖 3/9 种类型，74% 的股票
    永远拿不到信号。现在动量直接从 industry_daily 算，**不发任何网络请求**。
    """
    if market != "cn":
        return None
    try:
        from scripts.industry_signals import get_signal_for_stock
        return get_signal_for_stock(code) or None
    except Exception:
        return None


def get_latest_daily_analysis(code):
    return db.get_latest_analysis(code, period="daily")


def get_job(job_id):
    return db.get_job(job_id)


def get_job_analysis(code):
    return db.get_latest_analysis(code)
