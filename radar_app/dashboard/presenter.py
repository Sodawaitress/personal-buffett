"""Dashboard presentation helpers."""

from datetime import datetime, timedelta

from radar_app.shared.i18n import load_strings
from radar_app.shared.market import MARKET_CURRENCY, detect_market
from radar_app.shared.runtime import CN_TZ


def present_portfolio_brief(portfolio_brief):
    if not portfolio_brief or not portfolio_brief.get("created_at"):
        return portfolio_brief
    try:
        utc_time = datetime.strptime(portfolio_brief["created_at"][:16], "%Y-%m-%d %H:%M")
        portfolio_brief = dict(portfolio_brief)
        portfolio_brief["created_at_cst"] = (utc_time + timedelta(hours=8)).strftime("%H:%M")
    except Exception:
        portfolio_brief = dict(portfolio_brief)
        portfolio_brief["created_at_cst"] = ""
    return portfolio_brief


def index_alert(stock, t):
    grade = (stock.get("grade") or "—").replace("+", "").replace("-", "")
    if grade in ("C", "D"):
        return "warn", t["alert_warn_grade"].format(grade=stock.get("grade", "—"))
    net = stock.get("main_net")
    if net is not None and net < -0.5:
        return "warn", t["alert_warn_outflow"].format(net=net)
    conclusion = stock.get("conclusion") or ""
    if conclusion in ("卖出", "减持", "Sell", "Reduce"):
        return "warn", t["alert_warn_conclusion"].format(conclusion=conclusion)
    reasoning = (stock.get("reasoning") or "")[:45]
    return "ok", (reasoning + "…") if reasoning else t["alert_ok_fallback"]


def brief_alert(stock, t):
    grade = (stock.get("grade") or "—").replace("+", "").replace("-", "")
    if grade in ("C", "D"):
        return "warn", t["alert_warn_grade"].format(grade=stock.get("grade", "—"))
    net = stock.get("main_net")
    if net is not None and net < -0.5:
        return "warn", t["alert_warn_outflow"].format(net=net)
    conclusion = stock.get("conclusion", "")
    if conclusion in ("卖出", "减持", "Sell", "Reduce"):
        return "warn", conclusion
    reasoning = (stock.get("reasoning") or "")[:60]
    return "ok", (reasoning + "…") if reasoning else t["alert_ok_fallback"]


def present_index_stock(row, snapshot, pending_job, locale="en"):
    analysis = snapshot["analysis"]
    fund_flow = snapshot["fund_flow"]
    market = row.get("market") or detect_market(row.get("stock_code") or row.get("code"))
    stock = {
        "code": row.get("stock_code") or row.get("code"),
        "name": row.get("name", row.get("stock_code") or row.get("code")),
        "market": market,
        "currency": MARKET_CURRENCY.get(market, "$"),
        "price": snapshot["price"].get("price"),
        "change_pct": snapshot["price"].get("change_pct"),
        "grade": analysis.get("grade", "—") if analysis else "—",
        "conclusion": analysis.get("conclusion", "") if analysis else "",
        "reasoning": (analysis.get("reasoning", "") or "")[:120] if analysis else "",
        "has_letter": bool(analysis and analysis.get("letter_html")),
        "main_net": fund_flow.get("main_net") if fund_flow else None,
        "pending_job": pending_job,
        "analysis_date": analysis.get("analysis_date", "") if analysis else "",
    }
    stock["alert_level"], stock["alert_reason"] = index_alert(stock, load_strings(locale))
    return stock


def present_brief_stock(row, snapshot, locale="en"):
    analysis = snapshot["analysis"]
    fund_flow = snapshot["fund_flow"]
    market = row.get("market") or detect_market(row.get("stock_code") or row.get("code"))
    stock = {
        "code": row.get("stock_code") or row.get("code"),
        "name": row.get("name", row.get("stock_code") or row.get("code")),
        "market": market,
        "currency": MARKET_CURRENCY.get(market, "$"),
        "grade": analysis.get("grade", "—") if analysis else "—",
        "conclusion": analysis.get("conclusion", "") if analysis else "",
        "reasoning": (analysis.get("reasoning", "") or "")[:80] if analysis else "",
        "main_net": fund_flow.get("main_net") if fund_flow else None,
    }
    stock["alert_level"], stock["alert_reason"] = brief_alert(stock, load_strings(locale))
    return stock


def present_intl_news(intl_news, market):
    fear_greed = market.get("fear_greed", {})
    cny = market.get("cny_usd", {})
    items = list(intl_news)
    if fear_greed and fear_greed.get("score") is not None:
        items.insert(
            0,
            {
                "title": f"CNN Fear & Greed: {fear_greed['score']} — {fear_greed.get('label', '')}. {fear_greed.get('buffett', '')}",
                "link": "",
                "source": "CNN Markets",
                "time": "",
                "section": "Macro",
            },
        )
    if cny and cny.get("rate"):
        items.insert(
            1,
            {
                "title": f"USD/CNY {cny['rate']} — {cny.get('direction', '')}",
                "link": "",
                "source": "汇率",
                "time": "",
                "section": "Macro",
            },
        )
    return items


def now_label():
    return datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")
