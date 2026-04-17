"""Portfolio service helpers."""

from datetime import datetime

import db
from radar_app.legacy.portfolio import generate_portfolio_brief
from radar_app.shared.market import detect_market
from radar_app.shared.runtime import CN_TZ


def generate_brief_for_user(user_id, locale):
    watchlist = db.get_user_watchlist(user_id)
    stocks_data = []
    for row in watchlist:
        code = row.get("stock_code") or row.get("code")
        market = row.get("market") or detect_market(code)
        analysis = db.get_latest_analysis(code, period="daily")
        fund_flow = db.get_fund_flow(code) if market == "cn" else {}
        if analysis:
            stocks_data.append(
                {
                    "code": code,
                    "name": row.get("name", code),
                    "grade": analysis.get("grade"),
                    "conclusion": analysis.get("conclusion"),
                    "reasoning": analysis.get("reasoning"),
                    "moat": analysis.get("moat"),
                    "behavioral": analysis.get("behavioral"),
                    "main_net": fund_flow.get("main_net") if fund_flow else None,
                }
            )

    snapshot = db.get_market_snapshot()
    market_data = snapshot.get("data", {}) if snapshot else {}
    macro, summary = generate_portfolio_brief(stocks_data, market_data, locale=locale)

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    db.save_portfolio_brief(user_id, today, macro, summary)
    return {"ok": True, "macro": macro, "summary": summary}
