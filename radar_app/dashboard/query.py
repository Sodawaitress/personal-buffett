"""Dashboard data access helpers."""

import db
from radar_app.legacy.market_data import (
    NZ_SECTORS,
    fetch_cn_market_news,
    fetch_fomc_news,
    fetch_nz_market_news,
    fetch_nzx50,
    fetch_rbnz_news,
)
from radar_app.shared.jobs import get_recent_pending_job


def list_active_watchlist(user_id):
    return [
        row
        for row in db.get_user_watchlist(user_id)
        if row.get("status", "watching") != "sold"
    ]


def get_pending_job(code):
    return get_recent_pending_job(code)


def get_stock_snapshot(code, market):
    return {
        "price": db.get_latest_price(code),
        "analysis": db.get_latest_analysis(code, period="daily"),
        "fund_flow": db.get_fund_flow(code) if market == "cn" else {},
    }


def get_market_snapshot():
    market = {}
    try:
        market["nzx50"] = fetch_nzx50()
        market["nz_sectors"] = NZ_SECTORS
    except Exception:
        pass
    try:
        snapshot = db.get_market_snapshot()
        if snapshot:
            market_data = snapshot.get("data", {})
            for key in ("fear_greed", "cny_usd", "cn_indices", "commodities"):
                if market_data.get(key):
                    market[key] = market_data[key]
    except Exception:
        pass
    return market


def get_local_news(region="nz"):
    local_news = []
    if region == "cn":
        try:
            local_news = fetch_cn_market_news(limit=10)
        except Exception:
            pass
    else:
        try:
            for item in fetch_nz_market_news()[:8]:
                local_news.append({**item, "section": "Market"})
        except Exception:
            pass
        try:
            for item in fetch_rbnz_news(limit=3):
                local_news.append({**item, "section": "RBNZ"})
        except Exception:
            pass
    return local_news


def get_intl_stock_news(stocks):
    intl_news = []
    try:
        cn_codes = [stock["code"] for stock in stocks if stock["market"] in ("cn", "hk")]
        seen = set()
        for code in cn_codes[:15]:
            stock_info = db.get_stock(code)
            stock_name = stock_info.get("name", code) if stock_info else code
            for item in db.get_stock_news(code, days=3):
                key = item.get("title", "")[:40]
                if key and key not in seen:
                    seen.add(key)
                    intl_news.append(
                        {
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "source": item.get("source", stock_name),
                            "time": item.get("publish_time", ""),
                            "section": stock_name,
                        }
                    )
        intl_news.sort(key=lambda item: item.get("time", ""), reverse=True)
        return intl_news[:10]
    except Exception:
        return []


def get_fomc_news_items(limit=2):
    try:
        return [{**item, "section": "FOMC"} for item in fetch_fomc_news(limit=limit)]
    except Exception:
        return []


def get_reports_bundle():
    return {
        "reports": db.list_reports(limit=10),
        "latest_report": db.get_report(),
        "weekly_report": db.get_report(period="weekly"),
        "monthly_report": db.get_report(period="monthly"),
        "quarterly_report": db.get_report(period="quarterly"),
    }


def get_portfolio_brief(user_id, date):
    return db.get_portfolio_brief(user_id, date=date)
