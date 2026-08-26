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

_ETF_PASSIVE_KEYWORDS  = ("ETF", "联接", "指数", "LOF")
_STRONG_ACTIVE_KEYWORDS = ("社保", "QFII", "陆股通", "汇金", "养老", "险资")


def _get_fundamentals_with_age(code: str) -> tuple[dict, float]:
    """返回 (signals_dict, age_hours)，age 超过阈值时 margin 信号应跳过。"""
    row = _cached("fundamentals", code)
    if row is _MISS:
        with get_conn() as c:
            row = c.execute(
                "SELECT signals_json, updated_at FROM stock_fundamentals WHERE code=:code",
                {"code": code},
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
        updated = row["updated_at"]
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace(" ", "T"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=CN_TZ)
        age_h = max(0, (datetime.now(CN_TZ) - updated).total_seconds() / 3600)
    except Exception:
        pass
    return signals, age_h


# ── 信号定义与方向 ────────────────────────────────────────────────────
#
# direction: 'bull' = 看多信号, 'bear' = 看空信号
#            'attention' = **注意力信号，本身没方向**（US-167）
# weight: 信号强度权重
#
# US-167：调研原本写死成 bull。用户妈妈指出「机构接连两个月调研的红柱子，
# 但股价还是在跌 …… 调研到最后并不值得机构买，也不一定」——她是对的：
# 机构去看了公司，可能看完买，也可能看完不买、甚至卖。「有人在看」是
# 注意力，不是方向。方向由 _survey_direction() 从**调研之后的走势**推导；
# 推不出来就保持 attention，_calc_resonance 只数 bull/bear，attention 自然
# 不参与共振，不会再制造「看空在撤 + 机构在建仓」这种自相矛盾的展示。

_SIGNAL_DEFS = {
    "survey_visit":      {"label": "机构专程调研",  "direction": "attention", "weight": 2},
    "survey_active":     {"label": "机构调研活跃",  "direction": "attention", "weight": 1},
    "participation_spike": {"label": "机构参与度突增", "direction": "bull", "weight": 2},
    # US-178：标签必须落在数据的窗口之内。get_fund_flow 是
    # `ORDER BY date DESC LIMIT 1` —— **一天**的数据，说「持续」撑不住。
    #
    # US-185：但「（当日）」这个词本身有歧义。我写的时候指的是**窗口**
    # （这个数只覆盖一天），用户妈妈读成了**新鲜度**（这是今天的数）——
    # 而页面同时显示「前兆数据 15 小时前」「1天前」，于是她问
    # 「那我怎么去更新它呢？」。同一个词两种意思，正是我们一直在修的病。
    #
    # 改法：标签只说**是什么**，日期放进 detail 说**是哪天的**。
    # 具体日期没有歧义，也不需要她去猜「当日」指哪天。
    "main_flow_in":      {"label": "主力资金流入", "direction": "bull", "weight": 2},
    # 来自 stock_institute_hold_detail 的**单个季度**快照（`持股比例增幅 > 0` 的家数），
    # 且季报本身滞后约 2 个月。说「持续」同样越界。
    "inst_buying":       {"label": "机构增持（最新季报）", "direction": "bull", "weight": 1},
    "margin_surge_bull": {"label": "融资余额快速增加","direction": "bull", "weight": 1},
    "short_down":        {"label": "融券做空在减少", "direction": "bull", "weight": 1},
    "main_flow_out":     {"label": "主力资金流出", "direction": "bear", "weight": 2},
    "inst_selling":      {"label": "机构减持（最新季报）", "direction": "bear", "weight": 1},
    "short_up":          {"label": "融券做空在增加", "direction": "bear", "weight": 2},
    "margin_surge_bear": {"label": "融资余额快速减少","direction": "bear", "weight": 1},
}

RESONANCE_THRESHOLD = 2  # ≥2 个同向信号才上榜


# ── US-171：批量预取，把「每只查一次」压成「一条 IN 查询」 ────────────
#
# push-svc 从 3 分钟涨到 18 分钟，2026-08-25 撞上 20 分钟上限被杀，
# 妈妈那天的信一个字都没发出去。瓶颈不是算法，是**往返次数**：
# get_signal_conclusion 每只要查 4~5 次，妈妈 231 只 ≈ 1000 次；
# Neon 开了 pool_pre_ping（scale-to-zero 会断闲连接），每次 get_conn
# 还额外发一条 SELECT 1 —— 实际约 2000 次跨洋往返。
#
# 缓存是**显式开关**，不是默认长效：调用方 prefetch_for(codes) 装载、
# 用完 clear_prefetch()。默认 None = 走原路径，逐只查库。
# 这样单只查询（详情页）行为完全不变，只有批处理路径受益。
_PREFETCH: dict = {}


def prefetch_for(codes) -> None:
    """为一批股票预取信号所需的全部单行数据。只在批处理里用。"""
    codes = list(dict.fromkeys(codes))
    if not codes:
        return
    cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    # 调研事件回溯 60 天，后续窗口再 20 天，留足余量取 150 天
    pcut = (datetime.now() - timedelta(days=150)).strftime("%Y-%m-%d")
    pre, ff, fund, prices, surveys, series = {}, {}, {}, {}, {}, {}

    def _parts(seq, n=400):
        for i in range(0, len(seq), n):
            yield seq[i:i + n]

    for part in _parts(codes):
        keys = {f"c{i}": c for i, c in enumerate(part)}
        ph = ",".join(f":{k}" for k in keys)
        with get_conn() as c:
            # 每只取最新一条前兆缓存
            for r in c.execute(
                    f"""SELECT code, survey_json, short_json, partic_json, fetched_at
                        FROM stock_precursor_cache WHERE code IN ({ph})
                        ORDER BY code, fetched_at DESC""", keys):
                pre.setdefault(r["code"], dict(r))
            for r in c.execute(
                    f"""SELECT * FROM stock_fund_flow WHERE code IN ({ph})
                        ORDER BY code, date DESC""", keys):
                ff.setdefault(r["code"], dict(r))
            for r in c.execute(
                    f"""SELECT code, signals_json, updated_at FROM stock_fundamentals
                        WHERE code IN ({ph})""", keys):
                fund[r["code"]] = dict(r)
            # 两用：前 20 行给 _price_5d；完整序列给 US-167 的调研后续
            # （它要查任意历史日期的收盘价，取最近 20 行不够）。
            for r in c.execute(
                    f"""SELECT code, fetched_at, change_pct, price FROM stock_prices
                        WHERE code IN ({ph}) AND fetched_at >= :pcut
                        ORDER BY code, fetched_at DESC""", {**keys, "pcut": pcut}):
                lst = prices.setdefault(r["code"], [])
                if len(lst) < 20:
                    lst.append(dict(r))
                series.setdefault(r["code"], []).append(dict(r))
            for r in c.execute(
                    f"""SELECT code, event_date, n_inst, is_specific FROM survey_events
                        WHERE code IN ({ph}) AND event_date >= :cut
                        ORDER BY code, event_date DESC""", {**keys, "cut": cutoff}):
                surveys.setdefault(r["code"], []).append(dict(r))

    # series 按日期升序，好做「≥d 的第一条」
    for v in series.values():
        v.reverse()
    _PREFETCH.update({"precursor": pre, "fund_flow": ff, "fundamentals": fund,
                      "prices": prices, "surveys": surveys, "series": series,
                      "codes": set(codes)})


def clear_prefetch() -> None:
    _PREFETCH.clear()


def _cached(bucket: str, code: str):
    """命中预取返回值；未预取或不在本批里返回 _MISS，调用方走原路径。"""
    d = _PREFETCH.get(bucket)
    if d is None or code not in _PREFETCH.get("codes", ()):
        return _MISS
    return d.get(code)


_MISS = object()


def _parse_precursor_cache(code: str) -> dict:
    """从 stock_precursor_cache 读最新缓存，返回 {survey, short_selling, participation}.
    当缓存 survey 为空时，从 survey_events 永久表补回最近 60 天的事件。
    """
    row = _cached("precursor", code)
    if row is _MISS:
        with get_conn() as c:
            row = c.execute(
                "SELECT survey_json, short_json, partic_json, fetched_at "
                "FROM stock_precursor_cache WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
                {"code": code},
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
            perm_rows = _cached("surveys", code)
            if perm_rows is _MISS:
                cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
                with get_conn() as c:
                    perm_rows = c.execute(
                        "SELECT event_date, n_inst, is_specific FROM survey_events "
                        "WHERE code=:code AND event_date>=:cutoff ORDER BY event_date DESC",
                        {"code": code, "cutoff": cutoff},
                    ).fetchall()
            perm_rows = perm_rows or []
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


def _survey_direction(code: str, sv: dict) -> tuple[str | None, str]:
    """US-167：调研信号的方向 —— 看完之后股价怎么走。

    返回 (direction, detail_note)。direction 为 None 表示看不出来，
    调用方保持 _SIGNAL_DEFS 里的 'attention'（不参与多空共振）。

    只有**专项调研**且样本 ≥2 才给方向（本地回测：专项 72% / 普通 50%，
    普通调研跟抛硬币没区别）；判定逻辑全在 scripts/survey_followthrough.py，
    和详情页那块「调研之后发生了什么」用的是同一套，页面和榜单不会打架。
    """
    try:
        from scripts.survey_followthrough import build, db_price_lookup
        events = (sv.get("events") or [])[:8]   # 只查最近 8 次，控制扫描时的查询量
        if not events:
            return None, ""
        # US-171：批处理里价格已整批取回，逐个事件再查库就是几百次跨洋往返
        rows = _cached("series", code)
        if rows is _MISS:
            lookup = db_price_lookup(code)
        else:
            def lookup(d, _rows=rows or []):
                """取 d 当天或之后最近的收盘价（往后找 6 天，跨周末/长假）。
                语义必须与 db_price_lookup 一致，否则同一只股票在推送和
                详情页会给出不同结论。"""
                try:
                    from datetime import date as _d, timedelta as _td
                    d10 = str(d)[:10]
                    end = (_d.fromisoformat(d10) + _td(days=6)).isoformat()
                except (ValueError, TypeError):
                    return None
                for r in _rows:
                    f = str(r.get("fetched_at"))[:10]
                    if d10 <= f <= end:
                        return r.get("price") or None
                return None
        ft = build(events, lookup)
        d = ft.get("direction")
        if d not in ("bull", "bear"):
            return None, ""
        note = ("（调研后多数走强）" if d == "bull" else "（调研后多数走弱）")
        return d, note
    except Exception:
        return None, ""


def _detect_signals(code: str, precursor: dict, fund_flow: dict, signals: dict,
                    signals_age_h: float = 0) -> list[dict]:
    """
    对单只股票检测当前活跃信号列表。
    每个 signal: {key, label, direction, weight, detail}
    """
    found = []

    def add(key, detail="", direction=None):
        meta = _SIGNAL_DEFS.get(key, {})
        found.append({
            "key":       key,
            "label":     meta.get("label", key),
            # direction 可被调用方覆盖：调研类信号的方向是推导出来的，不是查表的
            "direction": direction or meta.get("direction", "neutral"),
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
            # 方向从「历次调研之后股价怎么走」推导（用全部历史事件，不只 30 天内）
            sv_dir, sv_note = _survey_direction(code, sv)
            specific = [e for e in events if e.get("is_specific")]
            if specific:
                latest = specific[0]
                add("survey_visit",
                    f"{latest.get('n_inst','')}家机构专项调研 · {latest.get('date','')[:10]}{sv_note}",
                    direction=sv_dir)
            else:
                latest = events[0]
                # survey_active 要求至少 3 家机构，1-2 家视为例行拜访
                n = int(latest.get("n_inst") or 0)
                if n >= 3:
                    add("survey_active",
                        f"{n}家机构调研 · {latest.get('date','')[:10]}{sv_note}",
                        direction=sv_dir)

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
                # US-185：把**数据实际是哪天的**写出来。资金流是逐日数据，
                # 而扫描每天只跑一次 —— 「当日」到底指今天还是上一个交易日，
                # 用户没法从字面判断，只能去猜。给日期就不用猜。
                _d = str(fund_flow.get("date") or "")[:10]
                _when = f"{_d[5:].replace('-', '-')} 收盘 · " if len(_d) == 10 else ""
                detail = (f"{_when}净占比 {mr:+.1f}%，"
                          f"净{'流入' if mn > 0 else '流出'} {abs(mn):.2f} 亿")
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

    # 当反向权重 >= 主方权重的 50%，标记为分歧（不算纯方向信号）
    minority_w = bear_w if direction == "bull" else bull_w
    dominant_w = bull_w if direction == "bull" else bear_w
    has_conflict = (direction != "mixed") and (dominant_w > 0) and (minority_w / dominant_w >= 0.5)

    return {
        "direction":        direction,
        "has_conflict":     has_conflict,
        "bull_count":       len(bull),
        "bear_count":       len(bear),
        "bull_weight":      bull_w,
        "bear_weight":      bear_w,
        "resonance_count":  count,
        "dominant_signals": dominant,
    }


def _calc_divergence(precursor: dict, signals: dict, signals_age_h: float = 0) -> dict:
    """
    机构背离分：量化消息面与机构真实行为的背离程度。
    返回 {total, level, action, breakdown: {short, inst_quality, survey_consistency}}
    分值范围 -6 到 +6；≤-3 出货陷阱，≥+4 强共振。
    """
    breakdown = {}

    # 1. 融券信号（margin_change_pct，正值=融券余额上升=做空加仓）
    short_score = 0
    if signals_age_h <= _SIGNALS_MAX_AGE_H:
        mp = signals.get("margin_change_pct")
        if mp is not None:
            try:
                mp = float(mp)
                if mp > 15:
                    short_score = -2
                elif mp > 5:
                    short_score = -1
                elif mp < -15:
                    short_score = 2
                elif mp < -5:
                    short_score = 1
                # else 0
            except (TypeError, ValueError):
                pass
    breakdown["short"] = short_score

    # 2. 机构持仓质量（inst_top 增减持方类型）
    inst_score = 0
    inst_top = signals.get("inst_top") or []
    if inst_top:
        increased = [h for h in inst_top if (h.get("change") or 0) > 0]
        decreased = [h for h in inst_top if (h.get("change") or 0) < 0]

        def _is_passive(name: str) -> bool:
            return any(kw in name for kw in _ETF_PASSIVE_KEYWORDS)

        def _is_strong_active(name: str) -> bool:
            return any(kw in name for kw in _STRONG_ACTIVE_KEYWORDS)

        active_out = any(not _is_passive(h.get("name", "")) for h in decreased)
        active_in  = any(_is_strong_active(h.get("name", "")) or
                         (not _is_passive(h.get("name", ""))) for h in increased)
        passive_only_in = increased and all(_is_passive(h.get("name", "")) for h in increased)

        if decreased and active_out:
            inst_score = -2
        elif decreased and not active_out:
            inst_score = -1
        elif increased and active_in and not passive_only_in:
            inst_score = 2
        elif passive_only_in:
            inst_score = 1
        # else 0
    breakdown["inst_quality"] = inst_score

    # 3. 调研-做空一致性
    survey_score = 0
    sv = precursor.get("survey") or {}
    events = sv.get("events") or []
    survey_active = False
    if events:
        try:
            latest_date = datetime.strptime(events[0]["date"][:10], "%Y-%m-%d")
            survey_active = (datetime.now() - latest_date).days <= 30
        except Exception:
            pass

    if survey_active:
        mp_val = signals.get("margin_change_pct")
        try:
            mp_val = float(mp_val) if mp_val is not None else None
        except (TypeError, ValueError):
            mp_val = None

        if mp_val is not None and mp_val > 5:
            survey_score = -2
        elif mp_val is not None and mp_val < -5:
            survey_score = 2
        else:
            survey_score = 1
    breakdown["survey_consistency"] = survey_score

    total = short_score + inst_score + survey_score

    if total <= -3:
        level, action = "trap",      "机构在利用消息出货，不要追"
    elif total <= 0:
        level, action = "mixed",     "消息面和机构行为不一致，观望"
    elif total <= 3:
        level, action = "supported", "机构行为与消息共振，可以关注"
    else:
        level, action = "resonance", "消息+机构+资金全面共振，真实机会"

    return {"total": total, "level": level, "action": action, "breakdown": breakdown}


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
                n_inst = 0
                try:
                    n_inst = int(events[0].get("n_inst") or 0)
                except (TypeError, ValueError):
                    n_inst = 0
                bars.append({
                    "key":       "survey",
                    "label":     "机构调研活跃度",
                    "pct":       pct,
                    # US-176：家数要说出来。1 家和 167 家在页面上原本长得一模一样
                    # （柱高按单只股票内部归一化），「一个人去看」被画成
                    # 和「一百六十七个人去看」同样满格。
                    "hint":      (f"最近一次调研 {age_days} 天前"
                                  + (f"，{n_inst} 家机构" if n_inst else "")
                                  + ("，30 天内触发" if pct < 100 else "")) if pct < 100 else "已触发",
                    "n_inst":    n_inst,
                    # US-167：调研是**注意力**，不是方向。机构去看了，可能看完买、
                    # 看完不买、甚至看完就卖。当初只改了 _SIGNAL_DEFS，
                    # 这个函数自己写死了 "bull" —— 于是 167 家（看空那只）和
                    # 1 家（看多那只）在页面上是同一种绿色。
                    "direction": "attention",
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
                # US-176：同 survey —— 参与度高只说明「机构在场」，不说明多空。
                # 参与度**突增**才是信号（participation_spike），那是另一条。
                "direction": "attention",
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


def _price_5d(code: str) -> float:
    """近 5 交易日累计涨跌幅（%），按天去重防日内多行重复计。"""
    rows = _cached("prices", code)
    if rows is _MISS:
        with get_conn() as c:
            rows = c.execute(
                "SELECT fetched_at, change_pct FROM stock_prices WHERE code=:c "
                "ORDER BY fetched_at DESC LIMIT 20",
                {"c": code},
            ).fetchall()
    rows = rows or []
    seen, chgs = set(), []
    for r in rows:
        d = str(r["fetched_at"])[:10]
        if d in seen or r["change_pct"] is None:
            continue
        seen.add(d)
        chgs.append(r["change_pct"])
        if len(chgs) >= 5:
            break
    return round(sum(chgs), 2) if chgs else 0.0


# US-177：判断「股价还没反应」要用多长的窗口
#
# 原来只看近 5 日（_price_5d）。2026-08-25 用户妈妈实拍反例：
# **中石科技 300684** 的推送写「机构在悄悄研究/建仓，**股价还没反应**
# → 最早的领先信号」，而它 4 个月里从 41 涨到 97（当时 86）—— **翻了一倍多**。
# 她的原话：「都长成这样了，他说股价还没反应」。
#
# 5 天窗口回答不了「反应了没有」。一只翻倍的股票在任意 5 天里都可能微跌，
# 于是系统在最不该喊「还没涨」的时候喊了「还没涨」，
# **而且是朝着让人买入的方向喊**。
#
# 修法：短窗口仍用来找「今天的背离」，但要先过一道长窗口的闸 ——
# 已经明显走过一段的，无论如何不能说「还没反应」。
_LEAD_LONG_DAYS = 60          # 长窗口：约 3 个月的交易日
_LEAD_ALREADY_RAN = 20.0      # 60 日累计涨幅超过这个数 = 已经反应过了
_LEAD_ALREADY_FELL = -20.0


def _price_change_over(code: str, days: int) -> float:
    """近 N 个交易日的累计涨跌幅（%），按天去重防日内多行重复计。

    数据不足时返回 0.0 —— 不是「没涨」，是「不知道」。调用方要当心：
    0.0 会让闸门放行，所以闸门只用于**否决**，不用于肯定。
    """
    rows = _cached("series", code)
    if rows is _MISS:
        with get_conn() as c:
            rows = c.execute(
                "SELECT fetched_at, change_pct FROM stock_prices WHERE code=:c "
                "ORDER BY fetched_at DESC LIMIT :n",
                {"c": code, "n": days * 2},
            ).fetchall()
        rows = rows or []
    else:
        rows = list(reversed(rows or []))       # series 是升序，这里要降序
    seen, chgs = set(), []
    for r in rows:
        d = str(r["fetched_at"])[:10]
        try:
            cp = r["change_pct"]
        except (KeyError, TypeError, IndexError):
            cp = None
        if d in seen or cp is None:
            continue
        seen.add(d)
        chgs.append(float(cp))
        if len(chgs) >= days:
            break
    return round(sum(chgs), 2) if chgs else 0.0


def smart_money_vs_price(code: str, resonance: dict) -> str | None:
    """机构/资金方向 vs 价格。真背离=强信号(≥3同向)且价格明显反向，稀有才值钱。

    两道窗口（US-177）：
      长窗口（60日）否决 —— 已经走过一大段的，不能说「还没反应」
      短窗口（5日）确认 —— 最近确实在反方向动
    """
    d = resonance.get("direction")
    if d not in ("bull", "bear") or resonance.get("resonance_count", 0) < 3:
        return None

    p60 = _price_change_over(code, _LEAD_LONG_DAYS)
    p5 = _price_5d(code)

    if d == "bull" and p5 <= -2:
        # 已经涨过一大段 → 「还没反应」是假的，不管这 5 天怎么走
        if p60 >= _LEAD_ALREADY_RAN:
            return None
        return "lead_bull"
    if d == "bear" and p5 >= 2:
        if p60 <= _LEAD_ALREADY_FELL:
            return None
        return "lead_bear"
    return None


_RESEARCH_KEYS = {"survey_visit", "survey_active", "participation_spike"}


def conclusion_text(resonance: dict, lead: str | None, code: str = "") -> str:
    """一句人话结论。以「机构在研究/参与」为主轴（研究→参与→资金→价格）。纯规则。

    ## US-182：「悄悄」「最早」「领先」都是关于「别人还不知道」的断言

    2026-08-26 用户妈妈实拍反例 —— **中远海控 601919**：系统写
    「机构在专程研究、**悄悄参与**这家公司（3个信号同向·**最早的领先信号**）」，
    而它已从 13.08 涨到 17.52（+34%），站上全部均线。她的原话：

        「他管这个叫悄悄参与」
        **「这已经是太明显了，人人都看得到」**

    根因：本函数有三条说「悄悄/最早/领先」的路径，而 US-177 只给其中一条
    （`lead == "lead_bull"`，走 smart_money_vs_price 的 60 日闸）加了价格闸门。
    另外两条 —— `has_research` 和「聪明钱在悄悄建仓」—— **判据里只有信号
    数量，完全没有「价格动没动」这一项**。

    这是同一个病的第四次复发（US-151/163/167/177 之后）。教训：
    **修一处「越界的措辞」时，要把所有说同类话的地方一起找出来**，
    否则只是把病灶搬了个位置。
    """
    cnt = resonance.get("resonance_count", 0)
    d = resonance.get("direction")
    dom_keys = {s.get("key") for s in resonance.get("dominant_signals", [])}
    has_research = bool(dom_keys & _RESEARCH_KEYS)

    # 已经走过一大段 = 不管信号多齐，都不能再说「悄悄」「最早」「领先」
    already_ran = False
    if code:
        try:
            p60 = _price_change_over(code, _LEAD_LONG_DAYS)
            already_ran = p60 >= _LEAD_ALREADY_RAN
        except Exception:
            already_ran = False

    if lead == "lead_bull":
        return "机构在悄悄研究/建仓、股价还没反应 → 最早的领先信号"
    if lead == "lead_bear":
        return "机构在撤、股价还没跌 → 领先看空信号"
    if resonance.get("has_conflict") or d == "mixed":
        return "多空分歧，暂看不清"
    if d == "bull":
        if already_ran:
            # 信号还是那些信号，但「早」这个字已经不成立了
            base = "机构在专程研究、也在参与" if has_research else "资金在流入"
            return f"{base}，但股价已经涨过一段了（{cnt}个信号同向·不算领先）"
        if has_research:
            return f"机构在专程研究、悄悄参与这家公司（{cnt}个信号同向·最早的领先信号）"
        return f"聪明钱在悄悄建仓（{cnt}个信号同向）"
    if d == "bear":
        return f"机构在减持/流出（{cnt}个信号同向）"
    return "多空分歧，暂看不清"


def get_signal_conclusion(code: str) -> dict | None:
    """单只股票的结论包（US-119 层1）：与首页榜单同一模型/措辞，保证点榜单进详情讲同一个故事。
    返回 {conclusion, lead, direction, resonance_count, confidence, signals} 或 None（无信号）。"""
    precursor = _parse_precursor_cache(code)
    fund_flow = _cached("fund_flow", code)
    if fund_flow is _MISS:
        fund_flow = get_fund_flow(code)
    fund_flow = fund_flow or {}
    raw_signals, signals_age_h = _get_fundamentals_with_age(code)
    detected = _detect_signals(code, precursor, fund_flow, raw_signals, signals_age_h)
    if not detected:
        return None
    resonance = _calc_resonance(detected)
    lead = smart_money_vs_price(code, resonance)
    return {
        "conclusion":      conclusion_text(resonance, lead, code),
        "lead":            lead,
        "direction":       resonance["direction"],
        "resonance_count": resonance["resonance_count"],
        "confidence":      "high" if resonance["resonance_count"] >= 3 else "mid",
        "signals":         detected,
    }


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

        resonance  = _calc_resonance(detected)
        divergence = _calc_divergence(precursor, raw_signals, signals_age_h)
        lead       = smart_money_vs_price(code, resonance)

        entry = {
            "code":            code,
            "name":            s.get("name") or code,
            "status":          s.get("status", "watching"),
            "signals":         detected,
            "resonance":       resonance,
            "divergence":      divergence,
            "lead":            lead,
            "conclusion":      conclusion_text(resonance, lead, code),
            "confidence":      "high" if resonance["resonance_count"] >= 3 else "mid",
            "precursor_age":   _cache_age_label(precursor.get("fetched_at", "")),
        }

        if resonance["direction"] != "mixed" and resonance["resonance_count"] >= RESONANCE_THRESHOLD:
            triggered.append(entry)
        else:
            bars = _calc_approaching(code, precursor, fund_flow, raw_signals, signals_age_h)
            if bars:
                entry["approaching_bars"] = bars
                approaching.append(entry)

    # 排序：领先背离置顶 → 信号总权重 → 信号数
    def _sort_key(item):
        sigs = item["resonance"]["dominant_signals"]
        total_weight = sum(s["weight"] for s in sigs)
        return (1 if item.get("lead") else 0, total_weight, item["resonance"]["resonance_count"])

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


def _cache_age_label(fetched_at_str) -> str:
    if not fetched_at_str:
        return ""
    try:
        fetched = fetched_at_str
        if isinstance(fetched, str):
            fetched = datetime.fromisoformat(fetched.replace(" ", "T"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=CN_TZ)
        age_h = max(0, (datetime.now(CN_TZ) - fetched).total_seconds() / 3600)
        if age_h < 1:
            return f"{int(age_h * 60)}分钟前"
        if age_h < 24:
            return f"{int(age_h)}小时前"
        return f"{int(age_h / 24)}天前"
    except Exception:
        return ""
