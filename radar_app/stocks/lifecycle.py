"""短线生命周期 · 阶段引擎（US-129）。

两个正交轴（比喻是串联法，数据必须真）：
  🧬 进化（长期·公司本身）：变强/变弱/稳 —— 护城河方向 + ROIC/ROE 趋势 + 评分。
  🎂 年龄（短线·周期）：胚胎→幼年→壮年→老年→迟暮 —— 领先信号 + 动能 + 估值。

每个判断都带"真信号依据"（evidence），不糊弄。规则式 v1，可调。
"""

_STAGE_LABELS = {
    "embryo":  ("🥚 胚胎期", "业务在悄悄变，还没人发现"),
    "young":   ("🐣 幼年",   "机构在偷偷建仓，散户还没听说"),
    "prime":   ("🦁 壮年",   "题材正热，大家都在追"),
    "old":     ("🐷 老年",   "涨过一大波，散户在接盘"),
    "decline": ("🦥 迟暮",   "机构在撤，往下掉"),
    "unknown": ("· 看不清", "当前信号不足，看不出明确阶段"),
}


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _pf(s):
    """'15.31%'/'8039.65亿'/'326.19亿' → float（同指标跨年比较，单位一致即可）。"""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("%", "").strip()
    mult = 1.0
    if "万亿" in t:
        t = t.replace("万亿", ""); mult = 1e4
    elif "亿" in t:
        t = t.replace("亿", "")
    elif "万" in t:
        t = t.replace("万", ""); mult = 1e-4
    try:
        return float(t) * mult
    except ValueError:
        return None


def _trend(vals):
    """vals 旧→新。+1 多年上行 / -1 下滑 / 0 平。"""
    v = [x for x in vals if x is not None]
    if len(v) < 3:
        return 0
    old, new = v[0], v[-1]
    if old == 0:
        return 1 if new > 0 else 0
    ch = (new - old) / abs(old)
    return 1 if ch > 0.10 else (-1 if ch < -0.10 else 0)


def _evolution(fund, analysis):
    """长期：进化(变强)/退化(变弱)/稳 + 依据。用多年营收/净利/毛利率/ROE趋势(US-137)。"""
    rows = list(reversed((fund or {}).get("annual") or []))  # 转旧→新
    sig = (fund or {}).get("signals") or {}
    ev, score = [], 0

    def _s(key):
        return [_pf(r.get(key)) for r in rows]

    rev_t = _trend(_s("revenue"))
    prof_t = _trend(_s("net_profit"))
    gm_t = _trend(_s("gross_margin"))
    roe_t = _trend(_s("roe"))
    if rev_t:  score += rev_t * 2;  ev.append("营收多年" + ("上行" if rev_t > 0 else "下滑"))
    if prof_t: score += prof_t * 2; ev.append("净利多年" + ("上行" if prof_t > 0 else "下滑"))
    if gm_t:   score += gm_t;       ev.append("毛利率" + ("走高" if gm_t > 0 else "走低"))
    if roe_t:  score += roe_t;      ev.append("ROE" + ("上行" if roe_t > 0 else "下滑"))

    moat = str(sig.get("moat_direction") or "")
    if any(w in moat for w in ("↑", "改善", "走强", "变宽")):
        score += 1; ev.append(f"护城河{moat}")
    elif any(w in moat for w in ("↓", "恶化", "走弱", "变窄")):
        score -= 1; ev.append(f"护城河{moat}")

    q = (analysis or {}).get("quant_score")
    if q is not None:
        if _num(q) >= 60: ev.append(f"评分 {int(_num(q))}（偏强）")
        elif _num(q) <= 35: ev.append(f"评分 {int(_num(q))}（偏弱）")

    if score >= 2:
        return {"direction": "up", "label": "📈 长期在变强", "evidence": ev[:4]}
    if score <= -2:
        return {"direction": "down", "label": "📉 长期在变弱", "evidence": ev[:4]}
    return {"direction": "flat", "label": "➖ 长期稳", "evidence": ev[:4]}


def _momentum(code):
    """近窗口涨跌幅（%）。"""
    try:
        import db
        ph = db.get_price_history(code, days=30) or []
    except Exception:
        return None
    prices = [(_num(p.get("price")), str(p.get("fetched_at") or "")) for p in ph if p.get("price")]
    prices = [p for p in prices if p[0] > 0]
    if len(prices) < 2:
        return None
    prices.sort(key=lambda x: x[1])   # 按时间升序
    old, new = prices[0][0], prices[-1][0]
    return (new - old) / old * 100 if old else None


def _recent_tender(code, days=30):
    """近 N 天中标（US-131，巨潮）——🥚胚胎期基本面前兆。"""
    try:
        from radar_app.data.core import get_conn
        from datetime import date, timedelta
        cut = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        with get_conn() as c:
            rows = c.execute(
                "SELECT event_date, summary, event_type FROM stock_events "
                "WHERE code=:c AND source='cninfo_tender' AND event_date>=:cut "
                "ORDER BY event_date DESC LIMIT 1",
                {"c": code, "cut": cut},
            ).fetchall()
        return dict(rows[0]) if rows else None
    except Exception:
        return None


# 🪙 元宝 = 已兑现的正面成果（果）。每颗一件真事，带日期。解禁等负面不算元宝。
_YUANBAO_TYPES = {
    "tender_win":              "中标",
    "big_contract":            "大单合同",
    "capacity":                "扩产投产",
    "earnings_report":         "财报披露",
    "earnings_forecast":       "业绩预告",
    "restructuring_announced": "重组",
}


def _recent_yuanbao(code, days=120, limit=10):
    """近 N 天已兑现成果 → [{type,label,date,summary}]（枝头元宝，可点看真事）。"""
    try:
        from radar_app.data.core import get_conn
        from datetime import date, timedelta
        cut = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        types = tuple(_YUANBAO_TYPES)
        ph = ", ".join(f":t{i}" for i in range(len(types)))
        params = {"c": code, "cut": cut, **{f"t{i}": t for i, t in enumerate(types)}}
        with get_conn() as c:
            rows = c.execute(
                f"SELECT event_date, summary, event_type FROM stock_events "
                f"WHERE code=:c AND event_type IN ({ph}) AND event_date>=:cut "
                f"ORDER BY event_date DESC LIMIT {int(limit)}",
                params,
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({
                "type": d.get("event_type"),
                "label": _YUANBAO_TYPES.get(d.get("event_type"), "成果"),
                "date": d.get("event_date"),
                "summary": (d.get("summary") or "")[:40],
            })
        return out
    except Exception:
        return []


def build_lifecycle(code):
    """返回 {evolution, stage, verdict}。仅 A 股信号完整；其他市场信号少，阶段多为 unknown。"""
    import db
    from radar_app.data.market import get_precursor_cache
    try:
        from radar_app.data.signal_events import get_signal_conclusion
        sc = get_signal_conclusion(code)
    except Exception:
        sc = None

    fund = db.get_fundamentals(code) or {}
    analysis = db.get_latest_analysis(code) or {}
    sig = fund.get("signals") or {}
    precursor = get_precursor_cache(code) or {}

    evolution = _evolution(fund, analysis)

    # ── 短线阶段：收集"真信号" ──
    detected = (sc or {}).get("signals") or []
    keys = {d.get("key"): d for d in detected}
    direction = (sc or {}).get("direction")     # bullish/bearish/mixed
    lead = bool((sc or {}).get("lead"))
    pe_pct = sig.get("pe_percentile_5y") if sig.get("pe_percentile_5y") is not None else fund.get("pe_percentile_5y")
    pe_pct = _num(pe_pct, default=-1)
    mom = _momentum(code)
    margin_dir = str(sig.get("margin_direction") or "")
    margin_pct = _num(sig.get("margin_change_pct"), default=0)
    inst_inc = int(_num(sig.get("inst_increased")))
    inst_dec = int(_num(sig.get("inst_decreased")))
    part = precursor.get("participation") if isinstance(precursor.get("participation"), dict) else {}
    part_trend = str(part.get("trend") or "")

    tender = _recent_tender(code)
    has_embryo = bool(tender)

    ev = []
    if tender:
        _tl = {"tender_win": "近期中标", "big_contract": "重大合同", "capacity": "扩产投产"}
        ev.append(f"{_tl.get(tender.get('event_type'), '重大动向')}：{(tender.get('summary') or '')[:22]}（{tender.get('event_date')}）")
    has_early_inst = any(k in keys for k in ("survey_visit", "survey_active", "participation_spike")) \
                     or lead or inst_inc > inst_dec
    hot = (mom is not None and mom >= 25) or margin_pct >= 15
    overheated = (pe_pct >= 70) or (mom is not None and mom >= 60)
    weakening = (direction == "bearish") or ("下降" in part_trend) or (inst_dec > inst_inc) \
                or (analysis.get("grade") in ("D", "D-"))

    for d in detected[:5]:
        ev.append(d.get("label") or d.get("key"))
    if mom is not None:
        ev.append(f"近30日 {mom:+.0f}%")
    if pe_pct >= 0:
        ev.append(f"PE 处 5 年 {pe_pct:.0f}% 分位")
    if margin_dir:
        ev.append(f"融资余额{margin_dir}")

    # 优先级：迟暮 > 老年 > 壮年 > 幼年 > 胚胎
    if weakening and not has_early_inst:
        stage = "decline"
    elif overheated and (margin_pct >= 10 or inst_dec >= inst_inc):
        stage = "old"
    elif hot and direction in ("bullish", "mixed"):
        stage = "prime"
    elif has_early_inst and (mom is None or mom < 25):
        stage = "young"
    elif has_embryo and not hot and not weakening:
        stage = "embryo"          # 中标等基本面前兆，机构还没进 → 胚胎期
    elif direction in ("bullish", "mixed") or detected:
        stage = "prime"           # 有资金/信号但不够早也不够热 → 归壮年
    else:
        stage = "unknown"

    label, plain = _STAGE_LABELS[stage]

    # ── 合成一句话（长期×短线 二象）──
    long_tag = {"up": "长期变强", "down": "长期变弱", "flat": "长期稳"}[evolution["direction"]]
    short_map = {"embryo": "刚冒头", "young": "还年轻", "prime": "正当红", "old": "已偏老", "decline": "在退潮", "unknown": "阶段不明"}
    short_tag = short_map[stage]
    if evolution["direction"] == "up" and stage in ("embryo", "young"):
        verdict = "好公司 + 还年轻 → 值得关注"
    elif evolution["direction"] == "down" and stage in ("old", "decline"):
        verdict = "变弱的公司 + 已到晚期 → 别碰"
    elif stage in ("old", "decline"):
        verdict = "已到晚期，别当接盘的人"
    elif evolution["direction"] == "up" and stage == "prime":
        verdict = "好公司但已涨过一波，别追高"
    elif stage == "young":
        verdict = "早期信号出现，可关注"
    else:
        verdict = f"{long_tag} · {short_tag}"

    return {
        "evolution": evolution,
        "stage": {"key": stage, "label": label, "plain": plain, "evidence": ev},
        "verdict": verdict,
        "yuanbao": _recent_yuanbao(code),   # 🪙 已兑现成果（果），枝头元宝
    }
