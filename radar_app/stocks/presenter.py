"""Stock detail presentation helpers."""

from datetime import date, datetime, timezone

from radar_app.data.market import get_precursor_cache
from radar_app.data.signal_events import _calc_divergence, _SIGNALS_MAX_AGE_H
from radar_app.legacy.pipeline import compute_trading_params
from radar_app.shared.market import MARKET_CURRENCY
from radar_app.shared.metric_hints import compute_metric_hints
from radar_app.shared.runtime import CN_TZ

try:
    from scripts.buffett_signals import (
        describe_margin_context,
        describe_survey_context,
        describe_participation_context,
        label_news_vs_institution,
        prophet_daily_score,
    )
    _SIGNAL_CTX_OK = True
except Exception:
    _SIGNAL_CTX_OK = False

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


def _news_direction(news: list) -> str:
    """Derive overall news direction from sentiment counts."""
    if not news:
        return "neutral"
    pos = sum(1 for n in news if (n.get("sentiment") or "") == "positive")
    neg = sum(1 for n in news if (n.get("sentiment") or "") == "negative")
    if pos > neg and pos > len(news) * 0.4:
        return "positive"
    if neg > pos and neg > len(news) * 0.4:
        return "negative"
    return "neutral"


def _inst_direction(divergence: dict, signals: dict) -> str:
    """Derive overall institutional direction from divergence + signals."""
    if divergence:
        level = divergence.get("level", "mixed")
        if level == "confirm_bull":
            return "bullish"
        if level in ("bear_trap", "sell_signal"):
            return "bearish"
    if signals:
        inc = signals.get("inst_increased", 0) or 0
        dec = signals.get("inst_decreased", 0) or 0
        if inc > dec + 1:
            return "bullish"
        if dec > inc + 1:
            return "bearish"
    return "neutral"


def _build_divergence_card(news_dir: str, inst_dir: str, divergence: dict) -> dict | None:
    """Build the divergence summary card for the market section header."""
    if inst_dir == "neutral":
        return None
    label_map = {
        ("positive", "bullish"):  ("consistent", "新闻看多，机构在加仓", "信号一致，关注买点"),
        ("positive", "bearish"):  ("danger",     "新闻看多，但机构在减仓", "注意「消息出货」——新闻可能掩盖机构撤退"),
        ("negative", "bullish"):  ("opportunity","新闻看空，但机构在布局", "可能是底部逆向机会，等待催化剂"),
        ("negative", "bearish"):  ("consistent", "新闻看空，机构同步撤退", "信号一致，暂时观望"),
        ("neutral",  "bullish"):  ("mild",       "消息面平静，机构在悄悄买入", "可观察，等正面催化剂"),
        ("neutral",  "bearish"):  ("mild",       "消息面平静，但机构在减仓", "留意是否有未公开的负面信号"),
    }
    entry = label_map.get((news_dir, inst_dir))
    if not entry:
        return None
    card_type, headline, note = entry
    action = (divergence or {}).get("action", "")
    return {
        "type": card_type,
        "headline": headline,
        "note": note,
        "action": action,
    }


def _build_survey_chart(precursor: dict) -> list:
    """机构调研近 6 个月按月聚合，供交互式柱状图（US-119）。
    返回 [{month:'2026-07', label:'7月', count:家数, visits:次数, methods:[...]}]，无数据返回 []。"""
    survey = (precursor or {}).get("survey") or {}
    events = survey.get("events") or []
    if not events:
        return []
    now = datetime.now(CN_TZ)
    # 近 6 个月的桶（含本月），时间正序
    buckets = {}
    order = []
    for i in range(5, -1, -1):
        y, m = now.year, now.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y}-{m:02d}"
        buckets[key] = {"month": key, "label": f"{m}月", "count": 0, "visits": 0, "methods": []}
        order.append(key)
    for e in events:
        key = str(e.get("date", ""))[:7]
        if key in buckets:
            b = buckets[key]
            b["count"] += int(e.get("n_inst", 0) or 0)
            b["visits"] += 1
            meth = e.get("method")
            if meth and meth not in b["methods"]:
                b["methods"].append(meth)
    rows = [buckets[k] for k in order]
    return rows if any(r["count"] or r["visits"] for r in rows) else []


def _build_prophet_series(code: str) -> dict:
    """预言家线（US-75）：机构前兆脚印按日累积成一条轨迹（SMFI 原理）。
    读 precursor_history 近 90 天，每日合成分累积 + 调研/参与度异动注释点。
    历史不足 5 天返回 {}（线太短没意义）。"""
    if not _SIGNAL_CTX_OK:
        return {}
    from radar_app.data.market import get_precursor_history
    hist = get_precursor_history(code, days=90)
    if len(hist) < 5:
        return {}
    # 调研事件在"首次出现在快照里"的那天标注（事件发生日常无快照/快照早于发布）；
    # seen 去重，首日只播种不加成，避免把窗口内旧事件一次性倾倒。
    series, cum, seen = [], 0.0, set()
    for idx, row in enumerate(hist):
        d_full = str(row.get("date") or "")[:10]
        new_inst = 0
        for e in (row.get("survey") or {}).get("events") or []:
            key = (str(e.get("date", ""))[:10], e.get("n_inst"), e.get("method"))
            if key not in seen:
                seen.add(key)
                if idx > 0:
                    new_inst += int(e.get("n_inst", 0) or 0)
        ds = prophet_daily_score(row.get("participation"), new_inst)
        cum = round(cum + ds["value"], 3)
        note = (f"{new_inst}家机构调研" if new_inst > 0
                else "参与度异动" if ds["spike"] else "")
        series.append({"d": d_full[5:], "v": cum, "note": note})
    tail = [p["v"] for p in series[-5:]]
    slope = tail[-1] - tail[0] if len(tail) >= 2 else 0
    return {
        "series": series,
        "n_days": len(series),
        "start_date": str(hist[0].get("date") or "")[:10],
        "latest_dir": "rising" if slope > 0.5 else "falling" if slope < -0.5 else "flat",
    }


def _build_signal_contexts(precursor: dict, signals: dict, price_change_pct: float) -> dict:
    """Compute cross-product signal contexts from precursor cache."""
    if not _SIGNAL_CTX_OK or not precursor:
        return {}
    survey    = precursor.get("survey") or {}
    short_s   = precursor.get("short_selling") or {}
    partic    = precursor.get("participation") or {}

    sv_events  = survey.get("events") or []
    sv_count   = len([e for e in sv_events if e.get("date", "")[:7] == datetime.now(CN_TZ).strftime("%Y-%m")])
    sv_avg     = survey.get("monthly_avg", 0) or 0
    sv_foreign = survey.get("has_foreign", False)
    sv_repeat  = survey.get("repeat_institution", False)

    sh_change  = short_s.get("change_pct", 0) or 0

    # 缓存里存的键是 latest / avg_30d（不是 *_pct）——之前读错键导致永远 0（US-119 修）
    pt_latest  = partic.get("latest", 0) or 0
    pt_avg     = partic.get("avg_30d", 0) or 0
    pt_trend   = partic.get("trend", "中性") or "中性"
    pt_spike   = bool(partic.get("spike"))

    try:
        margin_ctx = describe_margin_context(
            change_pct=sh_change,
            price_change_pct=price_change_pct,
            participation_vs_avg=pt_latest - pt_avg,
            participation_spike=pt_spike,
            survey_count_30d=sv_count,
            survey_avg_monthly=sv_avg,
        )
    except Exception:
        margin_ctx = {}

    try:
        survey_ctx = describe_survey_context(
            count_30d=sv_count,
            avg_monthly=sv_avg,
            has_foreign=sv_foreign,
            repeat_institution=sv_repeat,
            margin_change_pct=sh_change,
            participation_vs_avg=pt_latest - pt_avg,
        )
    except Exception:
        survey_ctx = {}

    # 参与度数据源当前为空（latest/avg 全 0）→ 不拿空数据当信号（US-119 realign）
    if pt_latest <= 0 and pt_avg <= 0:
        partic_ctx = {}
    else:
        try:
            partic_ctx = describe_participation_context(
                latest=pt_latest,
                avg_30d=pt_avg,
                trend=pt_trend,
                spike=pt_spike,
                price_change_pct=price_change_pct,
                margin_change_pct=sh_change,
            )
        except Exception:
            partic_ctx = {}

    # Raw params for knowledge card popups
    sv_events_list = survey.get("events") or []
    sv_specific = any(e.get("is_specific") for e in sv_events_list)
    sv_n_inst = sv_events_list[0].get("n_inst", 0) if sv_events_list else 0
    try:
        _d = sv_events_list[0].get("date", "")[:10] if sv_events_list else ""
        sv_days_ago = (datetime.now(CN_TZ).date() -
                       datetime.strptime(_d, "%Y-%m-%d").date()).days if _d else 999
    except Exception:
        sv_days_ago = 999

    if margin_ctx:
        margin_ctx["_kcard"] = {
            "change_pct": sh_change,
            "price_change_pct": price_change_pct,
            "pa_spike": pt_spike,
            "has_survey": sv_count > 0,
        }
    if survey_ctx:
        survey_ctx["_kcard"] = {
            "has_specific": sv_specific,
            "n_inst": sv_n_inst,
            "days_ago": sv_days_ago,
            "score": float(survey.get("score") or 0),
            "event_count": len(sv_events_list),
        }
    if partic_ctx:
        partic_ctx["_kcard"] = {
            "spike": pt_spike,
            "price_change_pct": price_change_pct,
            "short_increasing": sh_change > 0,
            "trend": pt_trend,
        }

    # US-119 realign：亮原始数据 + 来源（让用户能验证"数据对不对"，Fintel 同理）
    if survey_ctx:
        _last = sv_events_list[0].get("date", "")[:10] if sv_events_list else ""
        _ev = f"本月 {sv_count} 家调研（月均 {sv_avg:g}）"
        if _last:
            _ev += f" · 最近 {_last}"
            if sv_n_inst:
                _ev += f"（{sv_n_inst}家）"
        survey_ctx["evidence"] = _ev
        survey_ctx["source"] = "东财机构调研"
    if partic_ctx:
        partic_ctx["evidence"] = f"参与度 {pt_latest:g} · 30日均 {pt_avg:g}"
        partic_ctx["source"] = "东财机构参与度"
        partic_ctx["series"] = partic.get("series") or []  # 日频序列供折线图（旧缓存无则空）

    return {"margin": margin_ctx, "survey": survey_ctx, "participation": partic_ctx}


def _label_news(news: list, inst_dir: str) -> list:
    """Add consistency label to each news article."""
    if not _SIGNAL_CTX_OK or not news:
        return news or []
    result = []
    for n in (news or []):
        n = dict(n)
        n["consistency"] = label_news_vs_institution(n.get("sentiment") or "neutral", inst_dir)
        result.append(n)
    return result


def _build_position_insight(watchlist_entry, price_52w, current_price):
    """Compute holding position stats for US-93 card. Returns None if not applicable."""
    if not watchlist_entry:
        return None
    if watchlist_entry.get("status") != "holding":
        return None
    buy_price = watchlist_entry.get("buy_price")
    buy_date_str = watchlist_entry.get("buy_date")
    if not buy_price or not current_price:
        return None

    try:
        buy = float(buy_price)
        cur = float(current_price)
        if buy <= 0 or cur <= 0:
            return None
    except (TypeError, ValueError):
        return None

    float_pnl_pct = round((cur / buy - 1) * 100, 2)

    days_held = None
    annualized = None
    if buy_date_str:
        try:
            buy_dt = date.fromisoformat(str(buy_date_str)[:10])
            days_held = (date.today() - buy_dt).days
            if days_held > 0:
                annualized = round(((cur / buy) ** (365.0 / days_held) - 1) * 100, 1)
        except (ValueError, TypeError):
            pass

    w52_high = price_52w.get("high") if price_52w else None
    w52_low  = price_52w.get("low")  if price_52w else None
    buy_pct_52w = None
    current_pct_52w = None
    if w52_high and w52_low and w52_high > w52_low:
        buy_pct_52w     = round((buy - w52_low) / (w52_high - w52_low) * 100, 1)
        current_pct_52w = round((cur  - w52_low) / (w52_high - w52_low) * 100, 1)

    return {
        "buy_price":        round(buy, 2),
        "current_price":    round(cur, 2),
        "float_pnl_pct":    float_pnl_pct,
        "days_held":        days_held,
        "annualized":       annualized,
        "w52_high":         round(w52_high, 2) if w52_high else None,
        "w52_low":          round(w52_low, 2)  if w52_low  else None,
        "buy_pct_52w":      buy_pct_52w,
        "current_pct_52w":  current_pct_52w,
    }


def present_stock_page(bundle):
    fund = bundle["fund"]
    signals = fund.get("signals", {}) if fund else {}
    annual = fund.get("annual", []) if fund else []
    signals, annual = format_non_cn_financials(signals, annual, bundle["analysis"])

    now_utc = datetime.now(timezone.utc)
    market = bundle["market"]
    divergence = _build_divergence(bundle["code"], signals, market, fund)
    resonance = compute_resonance(
        signals, divergence,
        bundle["fund_flow"], bundle["north_bound"],
        bundle["news"], market,
    )

    # US-92: divergence card + signal contexts + labeled news
    news_dir = _news_direction(bundle["news"])
    inst_dir = _inst_direction(divergence, signals)
    divergence_card = _build_divergence_card(news_dir, inst_dir, divergence)

    price_change = ((bundle["price"] or {}).get("change_pct") or 0) if bundle["price"] else 0
    precursor = get_precursor_cache(bundle["code"]) if market == "cn" else {}
    signal_contexts = _build_signal_contexts(precursor, signals, price_change) if market == "cn" else {}
    survey_chart = _build_survey_chart(precursor) if market == "cn" else []
    prophet_series = _build_prophet_series(bundle["code"]) if market == "cn" else {}
    news_labeled = _label_news(bundle["news"], inst_dir)

    # US-119 层1：与首页榜单同款结论（点榜单进详情讲同一个故事），仅 A股
    signal_conclusion = None
    if market == "cn":
        try:
            from radar_app.data.signal_events import get_signal_conclusion
            signal_conclusion = get_signal_conclusion(bundle["code"])
        except Exception:
            signal_conclusion = None

    try:
        from flask import session as _sess
        _loc = _sess.get("locale", "en")
    except Exception:
        _loc = "zh"

    # US-141 便宜但没坏：估值分位 × 进化轴（复用 lifecycle 的进化轴，同一套判断不做两份）
    cheapness = None
    try:
        from radar_app.stocks.lifecycle import _evolution
        from scripts.buffett_signals import describe_cheapness

        _fund = bundle.get("fund") or {}
        _evo = _evolution(_fund, bundle.get("analysis"))
        cheapness = describe_cheapness(
            (_fund.get("signals") or {}).get("pe_percentile_5y") or _fund.get("pe_percentile_5y"),
            _evo.get("direction"),
            # 英文界面下不塞中文依据（evidence 来自 lifecycle，仍是 zh-only，见 US-148）
            _evo.get("evidence") if _loc == "zh" else [],
            locale=_loc,
        )
    except Exception:
        cheapness = None

    # US-142 谁在卖自己公司的股票（A股，半年窗口）
    insider = None
    if market == "cn":
        try:
            import db as _db
            from scripts.insider_moves import WINDOW_DAYS, describe_insider_activity

            _rows = _db.get_insider_changes(bundle["code"], days=WINDOW_DAYS)
            _r = describe_insider_activity(_rows, locale=_loc)
            # 全是机械交易/无记录时不占版面（无料不报，US-68）
            insider = _r if (_r.get("has_data") or _r.get("routine_skipped")) else None
        except Exception:
            insider = None

    current_price_val = (bundle["price"] or {}).get("price") if bundle["price"] else None
    position_insight = _build_position_insight(
        bundle.get("watchlist_entry"),
        bundle.get("price_52w", {}),
        current_price_val,
    )

    return {
        "stock": bundle["stock"],
        "price": bundle["price"],
        "news": news_labeled,
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
        "market": market,
        "meta": bundle["meta"],
        "events": bundle["events"],
        "material_events": bundle.get("material_events", []),
        "currency": MARKET_CURRENCY.get(market, "$"),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "trading_params": compute_trading_params(bundle["price"], signals, market=market),
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
        # US-119 层1 结论（与首页一致）
        "signal_conclusion": signal_conclusion,
        "survey_chart": survey_chart,
        # US-75 预言家线
        "prophet_series": prophet_series,
        # US-92 extras
        "divergence_card": divergence_card,
        "signal_contexts": signal_contexts,
        "precursor": precursor,
        "market_currency": MARKET_CURRENCY,
        # US-93
        "position_insight": position_insight,
        "cheapness": cheapness,
        "insider": insider,
        # US-94
        "analyst_consensus": bundle.get("analyst_consensus"),
        # US-95
        "industry_signal": bundle.get("industry_signal"),
        # metric hints — human-readable one-liners for PE/ROE/etc
        "metric_hints": compute_metric_hints(
            annual[0] if annual else None,
            signals,
            fund.get("pe_current") if fund else None,
            bundle["price"],
        ),
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
