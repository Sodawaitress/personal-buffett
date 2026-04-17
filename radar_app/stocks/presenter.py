"""Stock detail presentation helpers."""

from datetime import datetime, timezone

from radar_app.legacy.pipeline import compute_trading_params
from radar_app.shared.market import MARKET_CURRENCY
from radar_app.shared.runtime import CN_TZ


def format_non_cn_financials(signals, annual, analysis):
    if not signals or annual:
        return signals, annual

    if "roe" in signals and isinstance(signals["roe"], (int, float)):
        signals["roe"] = f"{signals['roe']*100:.1f}%"
    if "roa" in signals and isinstance(signals["roa"], (int, float)):
        signals["roa"] = f"{signals['roa']*100:.1f}%"
    if "gross_margin" in signals and isinstance(signals["gross_margin"], (int, float)):
        signals["gross_margin"] = f"{signals['gross_margin']*100:.1f}%"
    if "profit_margin" in signals and isinstance(signals["profit_margin"], (int, float)):
        signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
        signals["profit_margin"] = signals["net_margin"]
    if "debt_to_equity" in signals and isinstance(signals["debt_to_equity"], (int, float)):
        debt_to_equity = signals["debt_to_equity"]
        if debt_to_equity > 5:
            signals["debt_ratio"] = f"{debt_to_equity:.2f}x ⚠"
            signals["debt_ratio_note"] = "D/E ratio（非负债率%），数值偏高"
        else:
            signals["debt_ratio"] = f"{debt_to_equity:.2f}x"
            signals["debt_ratio_note"] = "D/E ratio（非负债率%）"

    signals["year"] = (
        analysis["analysis_date"][:4]
        if analysis and "analysis_date" in analysis
        else datetime.now(CN_TZ).strftime("%Y")
    )
    annual = [{
        "year": signals.get("year", "—"),
        "roe": signals.get("roe", "—"),
        "net_margin": signals.get("net_margin", "—"),
        "debt_ratio": signals.get("debt_ratio", "—"),
        "debt_ratio_note": signals.get("debt_ratio_note"),
        "profit_growth": "—",
    }]
    return signals, annual


def age_label(ts_str, now_utc):
    if not ts_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now_utc - dt
        minutes = int(diff.total_seconds() / 60)
        if minutes < 1:
            return "刚刚"
        if minutes < 60:
            return f"{minutes} 分钟前"
        if minutes < 1440:
            return f"{minutes // 60} 小时前"
        return f"{minutes // 1440} 天前"
    except Exception:
        try:
            date_value = datetime.strptime(str(ts_str)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days = (now_utc - date_value).days
            if days == 0:
                return "今天"
            if days == 1:
                return "昨天"
            return f"{days} 天前"
        except Exception:
            return "—"


def age_minutes(ts_str, now_utc):
    if not ts_str:
        return float("inf")
    try:
        dt = datetime.fromisoformat(str(ts_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now_utc - dt).total_seconds() / 60
    except Exception:
        try:
            date_value = datetime.strptime(str(ts_str)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return (now_utc - date_value).total_seconds() / 60
        except Exception:
            return float("inf")


def present_stock_page(bundle):
    fund = bundle["fund"]
    signals = fund.get("signals", {}) if fund else {}
    annual = fund.get("annual", []) if fund else []
    signals, annual = format_non_cn_financials(signals, annual, bundle["analysis"])

    now_utc = datetime.now(timezone.utc)
    return {
        "stock": bundle["stock"],
        "price": bundle["price"],
        "news": bundle["news"],
        "analysis": bundle["analysis"],
        "history": bundle["history"],
        "prices": bundle["prices"],
        "fund_flow": bundle["fund_flow"],
        "ff_hist": bundle["ff_hist"],
        "north_bound": bundle["north_bound"],
        "signals": signals,
        "annual": annual,
        "pe_current": fund.get("pe_current") if fund else None,
        "pe_percentile_5y": fund.get("pe_percentile_5y") if fund else None,
        "pb_current": fund.get("pb_current") if fund else None,
        "pb_percentile_5y": fund.get("pb_percentile_5y") if fund else None,
        "pending_job": bundle["pending_job"],
        "in_watchlist": bundle["in_watchlist"],
        "market": bundle["market"],
        "meta": bundle["meta"],
        "events": bundle["events"],
        "currency": MARKET_CURRENCY.get(bundle["market"], "$"),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "trading_params": compute_trading_params(bundle["price"], signals, market=bundle["market"]),
        "data_freshness": {
            "price": age_label(bundle["price"].get("fetched_at") if bundle["price"] else None, now_utc),
            "finance": age_label(fund.get("updated_at") if fund else None, now_utc),
            "analysis": age_label(bundle["analysis"].get("analysis_date") if bundle["analysis"] else None, now_utc),
        },
        "data_freshness_stale": {
            "price": age_minutes(bundle["price"].get("fetched_at") if bundle["price"] else None, now_utc) > 3 * 1440,
            "finance": age_minutes(fund.get("updated_at") if fund else None, now_utc) > 7 * 1440,
            "analysis": age_minutes(bundle["analysis"].get("analysis_date") if bundle["analysis"] else None, now_utc) > 3 * 1440,
        },
    }


def present_letter_payload(analysis):
    if not analysis:
        return {"letter": None}
    return {
        "letter": analysis.get("letter_html", ""),
        "grade": analysis.get("grade"),
        "conclusion": analysis.get("conclusion"),
        "date": analysis.get("analysis_date"),
    }


def present_job_payload(job, result):
    analysis = {}
    if result:
        analysis = {
            "grade": result.get("grade"),
            "conclusion": result.get("conclusion"),
            "reasoning": result.get("reasoning", "")[:150],
            "letter": result.get("letter_html", ""),
        }
    return {
        "status": job["status"],
        "code": job.get("code"),
        "log": job.get("log", ""),
        "error": job.get("error"),
        "analysis": analysis,
    }
