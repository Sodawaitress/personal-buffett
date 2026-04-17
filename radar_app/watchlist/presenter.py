"""Watchlist presentation helpers."""

from datetime import date as date_type

from radar_app.shared.market import MARKET_CURRENCY, detect_market

GRADE_ORDER = {"A": 1, "B+": 2, "B": 3, "B-": 4, "C+": 5, "C": 6, "D": 7}
CONCLUSION_ORDER = {"买入": 1, "持有": 2, "观察": 3, "减持": 4, "卖出": 5}


def present_watchlist_stock(row, snapshot):
    code = row.get("stock_code") or row.get("code")
    market = row.get("market") or detect_market(code)
    analysis = snapshot["analysis"]
    fund = snapshot["fund"]
    signals = fund.get("signals", {}) if fund else {}
    grade = analysis.get("grade", "") if analysis else ""
    conclusion = analysis.get("conclusion", "") if analysis else ""

    return {
        "code": code,
        "name": row.get("name", code),
        "market": market,
        "currency": MARKET_CURRENCY.get(market, "$"),
        "price": snapshot["price"].get("price"),
        "change_pct": snapshot["price"].get("change_pct"),
        "grade": grade or "—",
        "grade_sort": GRADE_ORDER.get(grade, 99),
        "conclusion": conclusion,
        "conclusion_sort": CONCLUSION_ORDER.get(conclusion, 99),
        "reasoning": (analysis.get("reasoning", "") or "")[:120] if analysis else "",
        "has_letter": bool(analysis and analysis.get("letter_html")),
        "pending_job": snapshot["pending_job"],
        "analysis_date": analysis.get("analysis_date", "") if analysis else "",
        "moat_direction": signals.get("moat_direction", ""),
        "roic_latest": signals.get("roic_latest"),
        "fcf_quality": signals.get("fcf_quality_avg"),
        "status": row.get("status", "watching"),
        "buy_date": row.get("buy_date"),
        "buy_price": row.get("buy_price"),
        "sell_date": row.get("sell_date"),
        "sell_price": row.get("sell_price"),
        "entry_grade": row.get("entry_grade"),
    }


def calc_performance_stats(rows):
    with_return = [row for row in rows if row.get("return_pct") is not None]
    if not with_return:
        return {}

    winners = [row for row in with_return if row["return_pct"] > 0]
    graded = [row for row in with_return if row.get("entry_grade") in ("A", "B+", "B")]
    grade_wins = [row for row in graded if row["return_pct"] > 0]

    return {
        "total": len(with_return),
        "win_rate": len(winners) / len(with_return) * 100,
        "avg_return": sum(row["return_pct"] for row in with_return) / len(with_return),
        "grade_acc": len(grade_wins) / len(graded) * 100 if graded else None,
        "grade_n": len(graded),
    }


def present_performance_row(row, quote, today):
    code = row["code"]
    cur_price = quote.get("price")
    market = row.get("market", "cn")
    entry = row.get("buy_price") or (quote.get("price") if not row.get("buy_date") else None)

    try:
        days_held = (today - date_type.fromisoformat(row.get("buy_date") or row.get("added_at", "")[:10])).days
    except Exception:
        days_held = None

    perf = {
        **row,
        "code": code,
        "currency": MARKET_CURRENCY.get(market, "$"),
        "cur_price": cur_price,
        "days_held": days_held,
        "entry_price": entry,
        "return_pct": None,
        "annualized": None,
    }

    if entry and entry > 0:
        if row["status"] == "sold" and row.get("sell_price"):
            exit_price = row["sell_price"]
            ret = (exit_price - entry) / entry * 100
        elif row["status"] == "holding" and cur_price:
            exit_price = cur_price
            ret = (exit_price - entry) / entry * 100
        else:
            ret = None

        if ret is not None:
            perf["return_pct"] = ret
            if days_held and days_held > 0:
                perf["annualized"] = ((1 + ret / 100) ** (365 / days_held) - 1) * 100

    return perf
