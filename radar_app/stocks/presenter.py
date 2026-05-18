"""Stock detail presentation helpers."""

from datetime import datetime, timezone

from radar_app.data.market import get_precursor_cache
from radar_app.data.signal_events import _calc_divergence, _SIGNALS_MAX_AGE_H
from radar_app.legacy.pipeline import compute_trading_params
from radar_app.shared.market import MARKET_CURRENCY
from radar_app.shared.runtime import CN_TZ

_PASSIVE_KW = ("ETF", "联接", "指数", "LOF", "沪深300", "中证500", "中证1000")


def compute_resonance(signals: dict, divergence: dict, fund_flow: dict,
                      north_bound: dict, news: list, market: str) -> dict:
    """
    Build the 综合研判 synthesis for the signal tab.

    Signals are grouped into three independent sources:
      A – 内部人行为  (institutional / insider actual trades)
      B – 市场结构    (capital flows / short interest / analyst ratings)
      C – 新闻情绪    (news sentiment)

    Cross-group resonance: each group in agreement = +1 point (max 3).
    Intra-group conflicts cancel; same-group signals don't stack.
    """
    s = signals or {}
    groups: dict[str, str | None] = {}   # group → "bullish" | "bearish" | None
    bull_labels: list[str] = []
    bear_labels: list[str] = []

    # ── Group A: Institutional / insider behaviour ────────────────
    a_bull = a_bear = 0
    if market == "cn":
        bd = (divergence or {}).get("breakdown", {})
        iq = bd.get("inst_quality", 0)
        if iq >= 2:
            a_bull += 2; bull_labels.append("主动资金进场")
        elif iq == 1:
            a_bull += 1; bull_labels.append("资金结构偏主动")
        elif iq == -1:
            a_bear += 1; bear_labels.append("ETF掩护出货")
        elif iq <= -2:
            a_bear += 2; bear_labels.append("主动资金出逃")

        for h in s.get("inst_top", []):
            nm = h.get("name", "")
            if any(k in nm for k in _PASSIVE_KW):
                continue
            chg = h.get("change", 0) or 0
            if chg > 0:
                a_bull += 1
            elif chg < 0:
                a_bear += 1
        if a_bull > a_bear:
            bull_labels.append(f"主动基金增仓({a_bull}家↑)")
        elif a_bear > a_bull:
            bear_labels.append(f"主动基金减仓({a_bear}家↓)")
    else:
        insider = s.get("insider_us", {})
        activist = s.get("activist_13d", {})
        if activist.get("found"):
            a_bull += 2; bull_labels.append(f"{activist.get('name', activist.get('filer', '维权方'))}进场")
        if insider.get("cluster_buy"):
            a_bull += 2; bull_labels.append("高管Cluster买入")
        active_net = (s.get("inst_us") or {}).get("active_net_change", 0) or 0
        if active_net > 0.5:
            a_bull += 1; bull_labels.append("主动基金净增持")
        elif active_net < -0.5:
            a_bear += 1; bear_labels.append("主动基金净减持")

    if a_bull > 0 and a_bear == 0:
        groups["A"] = "bullish"
    elif a_bear > 0 and a_bull == 0:
        groups["A"] = "bearish"
    elif a_bull > 0 and a_bear > 0:
        groups["A"] = None   # intra-group conflict, no net signal

    # ── Group B: Market structure (flows / short / ratings) ───────
    b_bull = b_bear = 0
    if market == "cn":
        ff_net = (fund_flow or {}).get("main_net")
        if ff_net is not None:
            if ff_net > 0:
                b_bull += 1; bull_labels.append(f"主力净流入{ff_net:+.1f}亿")
            elif ff_net < 0:
                b_bear += 1; bear_labels.append(f"主力净流出{ff_net:.1f}亿")

        nb_net = (north_bound or {}).get("total_net")
        if nb_net is not None:
            if nb_net > 0:
                b_bull += 1; bull_labels.append(f"北向净流入")
            elif nb_net < 0:
                b_bear += 1; bear_labels.append(f"北向净流出")

        bd = (divergence or {}).get("breakdown", {})
        sh = bd.get("short", 0) or 0
        if sh >= 2:
            b_bull += 1; bull_labels.append("融券大幅撤退")
        elif sh <= -2:
            b_bear += 1; bear_labels.append("融券大幅加仓")
    else:
        inst_us = s.get("inst_us") or {}
        short_trend = inst_us.get("short_trend_pct")
        if short_trend is not None:
            if short_trend < -10:
                b_bull += 1; bull_labels.append("空头比例下降")
            elif short_trend > 20:
                b_bear += 1; bear_labels.append("空头比例上升")
        analyst_net = inst_us.get("top_analyst_net")
        if analyst_net is not None:
            if analyst_net >= 2:
                b_bull += 1; bull_labels.append(f"投行净升级{analyst_net}次")
            elif analyst_net <= -2:
                b_bear += 1; bear_labels.append(f"投行净降级{abs(analyst_net)}次")
        pos = s.get("price_position")
        if pos is not None and pos < 20:
            b_bull += 1; bull_labels.append("价格处52周低区")

    if b_bull > 0 and b_bear == 0:
        groups["B"] = "bullish"
    elif b_bear > 0 and b_bull == 0:
        groups["B"] = "bearish"
    elif b_bull > 0 and b_bear > 0:
        groups["B"] = None

    # ── Group C: News sentiment ───────────────────────────────────
    if news and len(news) >= 3:
        pos_ct = sum(1 for n in news if n.get("sentiment") == "positive")
        neg_ct = sum(1 for n in news if n.get("sentiment") == "negative")
        total = len(news)
        if pos_ct >= total * 0.5 and pos_ct > neg_ct:
            groups["C"] = "bullish"; bull_labels.append(f"新闻偏正面({pos_ct}/{total})")
        elif neg_ct >= total * 0.4 and neg_ct > pos_ct:
            groups["C"] = "bearish"; bear_labels.append(f"新闻偏负面({neg_ct}/{total})")

    # ── Score ─────────────────────────────────────────────────────
    bull_groups = [g for g, d in groups.items() if d == "bullish"]
    bear_groups = [g for g, d in groups.items() if d == "bearish"]
    n_bull, n_bear = len(bull_groups), len(bear_groups)
    max_score = max(len(groups), 1)

    if n_bull > n_bear:
        direction, score, main_labels = "bullish", n_bull, bull_labels
    elif n_bear > n_bull:
        direction, score, main_labels = "bearish", n_bear, bear_labels
    elif n_bull == 0 and n_bear == 0:
        return {"direction": "unknown", "score": 0, "max_score": max_score,
                "strongest_combo": None, "divergence_text": None}
    else:
        direction, score = "mixed", n_bull
        main_labels = bull_labels + bear_labels

    # Strongest combo (cross-group signals are most meaningful)
    combo_parts = main_labels[:3]
    strongest_combo = " × ".join(combo_parts) if len(combo_parts) >= 2 else (combo_parts[0] if combo_parts else None)

    # Divergence: pick the most notable counter-signal with an explanation
    divergence_text = None
    if n_bull > 0 and n_bear > 0:
        counter = (bear_labels if direction == "bullish" else bull_labels)
        if counter:
            lbl = counter[0]
            if "主动" in lbl or "基金" in lbl:
                if direction == "bullish":
                    divergence_text = f"{lbl}（可能是基金赎回压力，而非对公司判断）"
                else:
                    divergence_text = f"{lbl}（逆势方向，关注是否为底部布局信号）"
            elif "融券" in lbl or "空头" in lbl:
                divergence_text = f"{lbl}（可能是风险对冲，需结合催化剂判断）"
            else:
                divergence_text = lbl

    return {
        "direction": direction,
        "score": score,
        "max_score": max_score,
        "strongest_combo": strongest_combo,
        "divergence_text": divergence_text,
    }


def format_non_cn_financials(signals, annual, analysis):
    if not signals:
        return signals, annual

    # Normalize signals floats (yfinance returns decimal ratios, e.g. 0.235 for 23.5%)
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

    # Normalize annual rows (pipeline stores already-multiplied floats, e.g. 23.5 for 23.5%)
    for row in annual:
        if "roe" in row and isinstance(row["roe"], (int, float)):
            row["roe"] = f"{row['roe']:.1f}%"
        if "net_margin" in row and isinstance(row["net_margin"], (int, float)):
            row["net_margin"] = f"{row['net_margin']:.1f}%"
        if "debt_ratio" in row and isinstance(row["debt_ratio"], (int, float)):
            row["debt_ratio"] = f"{row['debt_ratio']:.1f}%"

    if not annual:
        # Build synthetic single-year entry from signals when pipeline has no annual data
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


def _build_divergence(code, signals, market, fund):
    """Compute divergence live (from stored fields) or fall back to precursor+signals."""
    if market != "cn" or not signals:
        return None
    # Prefer pre-computed value stored by pipeline
    if "divergence_score" in signals:
        return {
            "total":     signals["divergence_score"],
            "level":     signals.get("divergence_level", "mixed"),
            "action":    signals.get("divergence_action", ""),
            "breakdown": signals.get("divergence_breakdown", {}),
        }
    # Fall back: compute live (no survey data available here)
    try:
        updated_at = (fund or {}).get("updated_at", "")
        age_h = 0
        if updated_at:
            dt = datetime.fromisoformat(str(updated_at).replace(" ", "T"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        precursor = get_precursor_cache(code)
        return _calc_divergence(precursor, signals, signals_age_h=age_h)
    except Exception:
        return None


def present_stock_page(bundle):
    fund = bundle["fund"]
    signals = fund.get("signals", {}) if fund else {}
    annual = fund.get("annual", []) if fund else []
    signals, annual = format_non_cn_financials(signals, annual, bundle["analysis"])

    now_utc = datetime.now(timezone.utc)
    divergence = _build_divergence(bundle["code"], signals, bundle["market"], fund)
    resonance = compute_resonance(
        signals, divergence,
        bundle["fund_flow"], bundle["north_bound"],
        bundle["news"], bundle["market"],
    )
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
        "divergence": divergence,
        "annual": annual,
        "pe_current": fund.get("pe_current") if fund else None,
        "pe_percentile_5y": fund.get("pe_percentile_5y") if fund else None,
        "pb_current": fund.get("pb_current") if fund else None,
        "pb_percentile_5y": fund.get("pb_percentile_5y") if fund else None,
        "resonance": resonance,
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
