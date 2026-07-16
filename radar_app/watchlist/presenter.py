"""Watchlist presentation helpers."""

from datetime import date as date_type, timedelta

from radar_app.shared.market import MARKET_CURRENCY, detect_market

_COMPANY_TYPE_LABEL = {
    "mature_value":    "成熟价值",
    "growth_tech":     "成长科技",
    "financial":       "金融",
    "bank_insurance":  "银行保险",
    "cycle_position":  "周期",
    "dividend_safety": "高息防御",
    "survival_check":  "困境重整",
    "speculative":     "投机",
    "distressed":      "困境",
    "etf":             "ETF/基金",
    "other":           "其他",
}

GRADE_ORDER = {"A": 1, "B+": 2, "B": 3, "B-": 4, "C+": 5, "C": 6, "D": 7}
CONCLUSION_ORDER = {"买入": 1, "持有": 2, "观察": 3, "减持": 4, "卖出": 5}


def present_watchlist_stock(row, snapshot, avg_sentiment=None):
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
        "is_poor": grade in ("D", "D-"),  # 差评沉底（US-125）
        "conclusion": conclusion,
        "conclusion_sort": CONCLUSION_ORDER.get(conclusion, 99),
        "reasoning": (analysis.get("reasoning", "") or "")[:120] if analysis else "",
        "has_letter": bool(analysis and analysis.get("letter_html")),
        "pending_job": snapshot["pending_job"],
        "analysis_date": analysis.get("analysis_date", "") if analysis else "",
        "moat_direction": signals.get("moat_direction", ""),
        "roic_latest": signals.get("roic_latest"),
        "fcf_quality": signals.get("fcf_quality_avg"),
        "avg_sentiment": avg_sentiment,
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


def _cat(return_pct):
    """Categorise a return into success / learning / neutral."""
    if return_pct > 3:
        return "success"
    if return_pct < -3:
        return "learning"
    return "neutral"


def _accuracy(subset):
    """(accuracy_pct, n_success, n_learning) — neutral rows excluded from denominator."""
    s = sum(1 for r in subset if r["_cat"] == "success")
    l = sum(1 for r in subset if r["_cat"] == "learning")
    denom = s + l
    return (round(s / denom * 100) if denom else None), s, l


def calc_judgment_growth(rows):
    """US-39 · 「你的眼光在变准吗」computation.

    Filters to rows with strong buy calls (A/B+), buy_price, buy_date,
    and a computed return_pct. Returns None when sample < 3.
    """
    cutoff_date = (date_type.today() - timedelta(days=90)).isoformat()

    qualified = [
        r for r in rows
        if r.get("entry_grade") in ("A", "B+")
        and r.get("buy_price")
        and r.get("buy_date")
        and r.get("return_pct") is not None
    ]

    if len(qualified) < 3:
        return None

    # Attach category to each row (non-destructive copy)
    for r in qualified:
        r["_cat"] = _cat(r["return_pct"])

    overall_acc, s_all, l_all = _accuracy(qualified)
    n_neutral = len(qualified) - s_all - l_all

    # Time-split
    recent  = [r for r in qualified if (r.get("buy_date") or "") >= cutoff_date]
    earlier = [r for r in qualified if (r.get("buy_date") or "") <  cutoff_date]

    trend = None
    trend_pct = None
    recent_acc = earlier_acc = None
    if len(recent) >= 3 and len(earlier) >= 3:
        recent_acc,  _, _ = _accuracy(recent)
        earlier_acc, _, _ = _accuracy(earlier)
        if recent_acc is not None and earlier_acc is not None:
            diff = recent_acc - earlier_acc
            trend_pct = round(diff)
            trend = "improving" if diff >= 10 else ("declining" if diff <= -10 else "steady")

    # Per-company-type accuracy (≥ 3 samples)
    type_groups: dict = {}
    for r in qualified:
        ct = r.get("company_type") or "other"
        type_groups.setdefault(ct, []).append(r)

    type_accuracy = []
    for ct, group in type_groups.items():
        if len(group) >= 3:
            acc, s, _ = _accuracy(group)
            if acc is not None:
                type_accuracy.append({
                    "type": ct,
                    "label": _COMPANY_TYPE_LABEL.get(ct, ct),
                    "accuracy": acc,
                    "success": s,
                    "total": len(group),
                })
    type_accuracy.sort(key=lambda x: -x["accuracy"])

    return {
        "total":        len(qualified),
        "success":      s_all,
        "learning":     l_all,
        "neutral":      n_neutral,
        "accuracy":     overall_acc,
        "recent_n":     len(recent),
        "earlier_n":    len(earlier),
        "recent_acc":   recent_acc,
        "earlier_acc":  earlier_acc,
        "trend":        trend,
        "trend_pct":    trend_pct,
        "type_accuracy": type_accuracy[:3],
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
