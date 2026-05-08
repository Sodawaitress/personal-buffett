"""
US-76 最值得关注榜单：事件驱动 + 信号共振过滤。

每只自选股扫描5类信号，≥2个同向信号触发上榜。
无上榜时展示"接近触发"进度，告知用户离触发还差多少。
"""

import json
from datetime import datetime, timedelta

from radar_app.data.core import CN_TZ, get_conn
from radar_app.data.stocks import get_fund_flow, get_user_watchlist

_SIGNALS_MAX_AGE_H = 48   # signals_json 超过这个小时数视为过期，不用 margin 信号


def _get_fundamentals_with_age(code: str) -> tuple[dict, float]:
    """返回 (signals_dict, age_hours)，age 超过阈值时 margin 信号应跳过。"""
    with get_conn() as c:
        row = c.execute(
            "SELECT signals_json, updated_at FROM stock_fundamentals WHERE code=?",
            (code,)
        ).fetchone()
    if not row:
        return {}, 999
    signals = {}
    try:
        signals = json.loads(row["signals_json"] or "{}") or {}
    except Exception:
        pass
    age_h = 999
    try:
        updated = datetime.fromisoformat((row["updated_at"] or "").replace(" ", "T"))
        age_h = (datetime.now() - updated).total_seconds() / 3600
    except Exception:
        pass
    return signals, age_h


# ── 信号定义与方向 ────────────────────────────────────────────────────
#
# direction: 'bull' = 看多信号, 'bear' = 看空信号
# weight: 信号强度权重

_SIGNAL_DEFS = {
    "survey_visit":      {"label": "机构专程调研",  "direction": "bull", "weight": 2},
    "survey_active":     {"label": "机构调研活跃",  "direction": "bull", "weight": 1},
    "participation_spike": {"label": "机构参与度突增", "direction": "bull", "weight": 2},
    "main_flow_in":      {"label": "主力持续流入",  "direction": "bull", "weight": 2},
    "inst_buying":       {"label": "机构持续增持",  "direction": "bull", "weight": 1},
    "margin_surge_bull": {"label": "融资余额快速增加","direction": "bull", "weight": 1},
    "short_down":        {"label": "融券做空在减少", "direction": "bull", "weight": 1},
    "main_flow_out":     {"label": "主力持续流出",  "direction": "bear", "weight": 2},
    "inst_selling":      {"label": "机构持续减持",  "direction": "bear", "weight": 1},
    "short_up":          {"label": "融券做空在增加", "direction": "bear", "weight": 2},
    "margin_surge_bear": {"label": "融资余额快速减少","direction": "bear", "weight": 1},
}

RESONANCE_THRESHOLD = 2  # ≥2 个同向信号才上榜


def _parse_precursor_cache(code: str) -> dict:
    """从 stock_precursor_cache 读最新缓存，返回 {survey, short_selling, participation}.
    当缓存 survey 为空时，从 survey_events 永久表补回最近 60 天的事件。
    """
    with get_conn() as c:
        row = c.execute(
            "SELECT survey_json, short_json, partic_json, fetched_at "
            "FROM stock_precursor_cache WHERE code=? ORDER BY fetched_at DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return {}
    rec = {}
    try:
        rec["survey"]        = json.loads(row["survey_json"]  or "null") or {}
        rec["short_selling"] = json.loads(row["short_json"]   or "null") or {}
        rec["participation"] = json.loads(row["partic_json"]  or "null") or {}
        rec["fetched_at"]    = row["fetched_at"] or ""
    except Exception:
        pass

    # 如果缓存里没有调研事件，从永久表补回最近 60 天
    cached_events = (rec.get("survey") or {}).get("events") or []
    if not cached_events:
        try:
            cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            with get_conn() as c:
                perm_rows = c.execute(
                    "SELECT event_date, n_inst, is_specific FROM survey_events "
                    "WHERE code=? AND event_date>=? ORDER BY event_date DESC",
                    (code, cutoff),
                ).fetchall()
            if perm_rows:
                events = [
                    {"date": r["event_date"], "n_inst": r["n_inst"],
                     "is_specific": bool(r["is_specific"]), "source": "survey_events"}
                    for r in perm_rows
                ]
                rec["survey"] = {**(rec.get("survey") or {}), "events": events}
        except Exception:
            pass

    return rec


def _detect_signals(code: str, precursor: dict, fund_flow: dict, signals: dict,
                    signals_age_h: float = 0) -> list[dict]:
    """
    对单只股票检测当前活跃信号列表。
    每个 signal: {key, label, direction, weight, detail}
    """
    found = []

    def add(key, detail=""):
        meta = _SIGNAL_DEFS.get(key, {})
        found.append({
            "key":       key,
            "label":     meta.get("label", key),
            "direction": meta.get("direction", "neutral"),
            "weight":    meta.get("weight", 1),
            "detail":    detail,
        })

    # ── 1. 机构调研（仅用 30 天内的事件）────────────────────────────
    sv = precursor.get("survey", {})
    if isinstance(sv, dict):
        cutoff_30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        events = [e for e in (sv.get("events") or [])
                  if str(e.get("date", ""))[:10] >= cutoff_30]
        if events:
            specific = [e for e in events if e.get("is_specific")]
            if specific:
                latest = specific[0]
                add("survey_visit", f"{latest.get('n_inst','')}家机构专项调研 · {latest.get('date','')[:10]}")
            else:
                latest = events[0]
                # survey_active 要求至少 3 家机构，1-2 家视为例行拜访
                n = int(latest.get("n_inst") or 0)
                if n >= 3:
                    add("survey_active", f"{n}家机构调研 · {latest.get('date','')[:10]}")

    # ── 2. 机构参与度 ─────────────────────────────────────────────
    pa = precursor.get("participation", {})
    if isinstance(pa, dict) and pa.get("spike"):
        latest_v = pa.get("latest", 0) or 0
        avg_v    = pa.get("avg_30d", 0) or 0
        diff_pct = round((latest_v - avg_v) / max(avg_v, 1) * 100, 1)
        add("participation_spike", f"参与度 {latest_v:.0f}（均值 {avg_v:.0f}，+{diff_pct}%）")

    # ── 3. 融券做空 ───────────────────────────────────────────────
    sh = precursor.get("short_selling", {})
    if isinstance(sh, dict) and sh.get("valid"):
        trend = sh.get("trend", "")
        if "增加" in trend:
            add("short_up", sh.get("desc", "")[:40])
        elif "减少" in trend:
            add("short_down", sh.get("desc", "")[:40])

    # ── 4. 主力资金（用 ratio 相对指标，>3% 才算有效信号）─────
    main_net   = fund_flow.get("main_net")
    main_ratio = fund_flow.get("main_ratio")
    if main_ratio is not None:
        try:
            mr = float(main_ratio)
            mn = float(main_net or 0)
            if abs(mr) >= 3:
                detail = f"净占比 {mr:+.1f}%，净{'流入' if mn > 0 else '流出'} {abs(mn):.2f} 亿"
                if mr > 0:
                    add("main_flow_in",  detail)
                else:
                    add("main_flow_out", detail)
        except (TypeError, ValueError):
            pass

    # ── 5. 机构持仓变动（至少2家同向才算有效信号）───────────────
    inc = int(signals.get("inst_increased") or 0)
    dec = int(signals.get("inst_decreased") or 0)
    if inc >= 2 and inc > dec:
        add("inst_buying",  f"{inc} 家增持，{dec} 家减持")
    elif dec >= 2 and dec > inc:
        add("inst_selling", f"{dec} 家减持，{inc} 家增持")

    # ── 6. 融资余额（仅用 48h 内的新鲜数据）────────────────
    margin_pct = signals.get("margin_change_pct")
    if margin_pct is not None and signals_age_h <= _SIGNALS_MAX_AGE_H:
        try:
            mp = float(margin_pct)
            if mp >= 15:
                add("margin_surge_bull", f"融资余额 +{mp:.1f}%（杠杆资金涌入）")
            elif mp <= -15:
                add("margin_surge_bear", f"融资余额 {mp:.1f}%（杠杆资金撤离）")
        except (TypeError, ValueError):
            pass

    return found


def _calc_resonance(signals: list[dict]) -> dict:
    """
    计算共振分数。
    返回: {direction: 'bull'|'bear'|'mixed', bull_count, bear_count, resonance_count, dominant_signals}
    """
    bull = [s for s in signals if s["direction"] == "bull"]
    bear = [s for s in signals if s["direction"] == "bear"]
    bull_w = sum(s["weight"] for s in bull)
    bear_w = sum(s["weight"] for s in bear)

    if bull_w >= bear_w and len(bull) >= RESONANCE_THRESHOLD:
        direction = "bull"
        dominant  = bull
        count     = len(bull)
    elif bear_w > bull_w and len(bear) >= RESONANCE_THRESHOLD:
        direction = "bear"
        dominant  = bear
        count     = len(bear)
    else:
        direction = "mixed"
        dominant  = signals
        count     = max(len(bull), len(bear))

    return {
        "direction":        direction,
        "bull_count":       len(bull),
        "bear_count":       len(bear),
        "resonance_count":  count,
        "dominant_signals": dominant,
    }


def _calc_approaching(code: str, precursor: dict, fund_flow: dict, signals: dict,
                      signals_age_h: float = 0) -> list[dict]:
    """
    计算各信号离触发阈值还差多少（0-100%，100=已触发）。
    用于空态时展示"快要发生什么"的进度条。
    """
    bars = []

    # 机构调研活跃度：30天内有调研 = 触发，60天内有 = 接近
    sv = precursor.get("survey", {})
    if isinstance(sv, dict):
        events = sv.get("events") or []
        if events:
            try:
                first_date = datetime.strptime(events[0]["date"][:10], "%Y-%m-%d")
                age_days = (datetime.now() - first_date).days
                pct = max(0, min(99, round((1 - age_days / 60) * 100)))
                bars.append({
                    "key":       "survey",
                    "label":     "机构调研活跃度",
                    "pct":       pct,
                    "hint":      f"最近一次调研 {age_days} 天前，30 天内触发" if pct < 100 else "已触发",
                    "direction": "bull",
                })
            except Exception:
                pass

    # 机构参与度：latest / (avg * 1.3) 进度
    pa = precursor.get("participation", {})
    if isinstance(pa, dict) and pa.get("valid") and not pa.get("spike"):
        latest_v = pa.get("latest", 0) or 0
        avg_v    = pa.get("avg_30d", 0) or 1
        threshold = avg_v * 1.3
        pct = min(99, round(latest_v / max(threshold, 1) * 100))
        if pct >= 50:
            bars.append({
                "key":       "participation",
                "label":     "机构参与度",
                "pct":       pct,
                "hint":      f"当前 {latest_v:.0f}，触发需 {threshold:.0f}（+30% 均值）",
                "direction": "bull",
            })

    # 融资余额变化：绝对值 / 15% 进度（仅用新鲜数据）
    margin_pct = signals.get("margin_change_pct")
    if margin_pct is not None and signals_age_h <= _SIGNALS_MAX_AGE_H:
        try:
            mp = abs(float(margin_pct))
            pct = min(99, round(mp / 15 * 100))
            if pct >= 30:
                direction = "bull" if float(margin_pct) > 0 else "bear"
                bars.append({
                    "key":       "margin",
                    "label":     "融资余额变化",
                    "pct":       pct,
                    "hint":      f"当前变化 {margin_pct:+.1f}%，触发阈值 ±15%",
                    "direction": direction,
                })
        except (TypeError, ValueError):
            pass

    # 主力资金：ratio 的绝对值 / 5% 进度（ratio > 5% 是强信号）
    main_ratio = fund_flow.get("main_ratio")
    if main_ratio is not None:
        try:
            mr = float(main_ratio)
            pct = min(99, round(abs(mr) / 5 * 100))
            if pct >= 20:
                direction = "bull" if mr > 0 else "bear"
                bars.append({
                    "key":       "fund_flow",
                    "label":     "主力资金强度",
                    "pct":       pct,
                    "hint":      f"净占比 {mr:+.1f}%，±5% 以上为强信号",
                    "direction": direction,
                })
        except (TypeError, ValueError):
            pass

    bars.sort(key=lambda x: x["pct"], reverse=True)
    return bars[:4]  # 最多展示4条


def get_watchlist_signals(user_id: int) -> dict:
    """
    主入口：扫描该用户所有持有/观察中的A股，
    返回 {triggered: [...], approaching: [...]}。

    triggered:  已达到 ≥2 信号共振的股票（排行榜）
    approaching: 未上榜但有 ≥1 信号接近阈值的股票（空态预览）
    """
    stocks = get_user_watchlist(user_id, status=None)
    cn_stocks = [s for s in stocks if s.get("market") == "cn"
                 and s.get("status") in ("holding", "watching")]

    triggered  = []
    approaching = []

    for s in cn_stocks:
        code = s["stock_code"]

        # 读数据
        precursor   = _parse_precursor_cache(code)
        fund_flow   = get_fund_flow(code)
        raw_signals, signals_age_h = _get_fundamentals_with_age(code)

        # 信号检测
        detected = _detect_signals(code, precursor, fund_flow, raw_signals, signals_age_h)
        if not detected:
            continue

        resonance = _calc_resonance(detected)

        entry = {
            "code":            code,
            "name":            s.get("name") or code,
            "status":          s.get("status", "watching"),
            "signals":         detected,
            "resonance":       resonance,
            "precursor_age":   _cache_age_label(precursor.get("fetched_at", "")),
        }

        if resonance["direction"] != "mixed" and resonance["resonance_count"] >= RESONANCE_THRESHOLD:
            triggered.append(entry)
        else:
            bars = _calc_approaching(code, precursor, fund_flow, raw_signals, signals_age_h)
            if bars:
                entry["approaching_bars"] = bars
                approaching.append(entry)

    # 排序：先按信号总权重降序，权重相同时再按信号数降序
    def _sort_key(item):
        sigs = item["resonance"]["dominant_signals"]
        total_weight = sum(s["weight"] for s in sigs)
        return (total_weight, item["resonance"]["resonance_count"])

    triggered.sort(key=_sort_key, reverse=True)
    approaching.sort(
        key=lambda x: max((b["pct"] for b in x.get("approaching_bars", [])), default=0),
        reverse=True,
    )

    return {
        "triggered":   triggered[:12],
        "approaching": approaching[:5],
        "scanned":     len(cn_stocks),
    }


def _cache_age_label(fetched_at_str: str) -> str:
    if not fetched_at_str:
        return ""
    try:
        fetched = datetime.fromisoformat(fetched_at_str.replace(" ", "T"))
        age_h = (datetime.now() - fetched).total_seconds() / 3600
        if age_h < 1:
            return f"{int(age_h * 60)}分钟前"
        if age_h < 24:
            return f"{int(age_h)}小时前"
        return f"{int(age_h / 24)}天前"
    except Exception:
        return ""
