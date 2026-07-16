# ── 共用关键词常量 ────────────────────────────────────────────────────────────
_KW_HIGH_NEG   = ["辞职", "离职", "被查", "立案", "违规", "处罚", "诉讼", "商誉减值", "暴雷"]
_KW_MID_NEG    = ["减持", "亏损", "下滑", "下降", "降级", "失败", "撤回", "退出"]
_KW_HIGH_POS   = ["回购", "增持", "大额分红", "创历史新高", "重大中标", "获批上市"]
_KW_MID_POS    = ["派息", "分红", "签约", "战略合作", "净利润增长", "获批", "中标"]
_KW_ST_NEG     = ["重整失败", "退市", "暂停上市", "破产清算", "终止重整"]
_KW_ST_POS     = ["重整通过", "债权人通过", "法院批准", "国资接盘", "重整计划获批", "摘帽"]
_KW_DILUTION   = ["转增", "配股", "增发", "资本公积转增"]
_KW_NOISE      = ["只个股", "家公司", "突破年线", "牛熊分界", "资金流向日报", "盘中播报", "技术分析", "K线", "涨跌幅排名"]
_KW_EN_HIGH_NEG = ["resign", "fired", "scandal", "lawsuit", "fraud", "downgrade",
                   "investigation", "bankruptcy", "loss", "crisis", "collapse"]
_KW_EN_MID_NEG  = ["decline", "miss", "lower", "reduce", "weak", "challenge", "concern"]
_KW_EN_HIGH_POS = ["upgrade", "acquisition", "record profit", "breakthrough", "approval",
                   "deal", "expansion", "beat estimate"]
_KW_EN_MID_POS  = ["partnership", "growth", "earnings", "profit", "revenue"]
# ─────────────────────────────────────────────────────────────────────────────

# 否定词：出现在关键词前 8 字内，则将情绪极性反转
def _dedupe_news(news_list: list, threshold: float = 0.6) -> list:
    """去除标题 bigram 重叠度 >= threshold 的近重复新闻，保留最早一条。"""
    def bigrams(text: str):
        return {text[i:i+2] for i in range(len(text) - 1)} if len(text) > 2 else {text}

    kept = []
    for n in news_list:
        title = n.get("title", "")
        bg = bigrams(title)
        duplicate = False
        for prev in kept:
            prev_bg = bigrams(prev.get("title", ""))
            union = bg | prev_bg
            if union and len(bg & prev_bg) / len(union) >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(n)
    return kept


_NEGATORS_CN = ["不", "未", "无", "终止", "取消", "撤回", "否认", "驳回", "拒绝", "失败"]
_NEGATORS_EN = ["no ", "not ", "cancel", "terminat", "withdraw", "deny", "reject", "fail"]


def _has_negation(title: str, keyword: str) -> bool:
    """检查关键词前8字是否有否定词，有则极性应反转。"""
    idx = title.find(keyword)
    if idx < 0:
        return False
    window = title[max(0, idx - 8): idx]
    tl = window.lower()
    return any(neg in window for neg in _NEGATORS_CN) or any(neg in tl for neg in _NEGATORS_EN)


def _verify_news_entity(news_list: list, company_name: str) -> list:
    """标记新闻主体可能不是本公司的条目（如'华闻期货'≠'华闻传媒'）。"""
    base = company_name
    for suffix in ["股份有限公司", "有限公司", "集团", "传媒", "科技", "投资", "控股", "实业"]:
        base = base.replace(suffix, "")
    base = base.replace("*ST", "").replace("ST", "").strip()
    if len(base) < 2:
        return news_list
    sibling_types = ["期货", "保险", "基金", "证券", "银行", "资管", "信托", "租赁"]
    siblings = [base + t for t in sibling_types]
    result = []
    for n in news_list:
        title = n.get("title", "")
        mismatch = next((s for s in siblings if s in title), None)
        if mismatch:
            n = {**n, "entity_mismatch": True,
                 "mismatch_reason": f"新闻主体疑似为'{mismatch}'（非本公司），已降权"}
        result.append(n)
    return result



def _analyze_news_signals(news: list, company_name: str = "") -> dict:
    HIGH_NEG      = _KW_HIGH_NEG
    MID_NEG       = _KW_MID_NEG
    HIGH_POS      = _KW_HIGH_POS
    MID_POS       = _KW_MID_POS
    ST_HIGH_NEG   = _KW_ST_NEG
    ST_HIGH_POS   = _KW_ST_POS
    DILUTION_WARN = _KW_DILUTION
    NOISE         = _KW_NOISE
    EN_HIGH_NEG   = _KW_EN_HIGH_NEG
    EN_MID_NEG    = _KW_EN_MID_NEG
    EN_HIGH_POS   = _KW_EN_HIGH_POS
    EN_MID_POS    = _KW_EN_MID_POS

    # 实体验证：过滤掉非本公司的同名兄弟公司新闻
    if company_name:
        news = _verify_news_entity(news, company_name)

    # 去重：同一事件多家媒体报道只算一次
    news = _dedupe_news(news)

    signal_counts = {"high_neg": 0, "mid_neg": 0, "high_pos": 0, "mid_pos": 0}
    sentiments = []
    key_signals = []
    impact_scores = []
    entity_mismatches = []
    dilution_warning = None
    st_signals = []

    for n in news:
        # 跳过实体不匹配的新闻（如"华闻期货"混入"华闻传媒"）
        if n.get("entity_mismatch"):
            entity_mismatches.append(n.get("mismatch_reason", "同名关联公司新闻"))
            continue

        title = n.get("title", "")
        title_lower = title.lower()
        if any(k in title_lower for k in NOISE):
            continue

        # ST/重整专项信号（优先匹配，不走通用路径）
        if any(k in title for k in ST_HIGH_NEG):
            signal_counts["high_neg"] += 1
            sentiments.append(-1.0)
            impact_scores.append(9)
            matched = next(k for k in ST_HIGH_NEG if k in title)
            key_signals.append(matched)
            st_signals.append(f"⚠️重整负面: {matched}")
            continue
        if any(k in title for k in ST_HIGH_POS):
            signal_counts["high_pos"] += 1
            sentiments.append(0.8)
            impact_scores.append(8)
            matched = next(k for k in ST_HIGH_POS if k in title)
            key_signals.append(matched)
            st_signals.append(f"✅重整进展: {matched}")
            continue
        if any(k in title for k in DILUTION_WARN):
            if not dilution_warning:
                dilution_warning = f"检测到稀释事件: {next(k for k in DILUTION_WARN if k in title)}（{title[:50]}）"
            sentiments.append(-0.3)
            impact_scores.append(6)
            continue

        # 找到匹配关键词，再检查是否有否定词（"未回购"/"取消分红"等）
        matched_neg_kw = next((k for k in HIGH_NEG if k in title_lower), next((k for k in EN_HIGH_NEG if k in title_lower), None))
        matched_mid_neg = next((k for k in MID_NEG if k in title_lower), next((k for k in EN_MID_NEG if k in title_lower), None))
        matched_pos_kw = next((k for k in HIGH_POS if k in title_lower), next((k for k in EN_HIGH_POS if k in title_lower), None))
        matched_mid_pos = next((k for k in MID_POS if k in title_lower), next((k for k in EN_MID_POS if k in title_lower), None))

        if matched_neg_kw:
            negated = _has_negation(title_lower, matched_neg_kw)
            if negated:
                signal_counts["mid_pos"] += 1
                sentiments.append(0.3)
                impact_scores.append(3)
                key_signals.append(f"[否定]{matched_neg_kw}")
            else:
                signal_counts["high_neg"] += 1
                sentiments.append(-1.0)
                impact_scores.append(8)
                key_signals.append(matched_neg_kw)
        elif matched_mid_neg:
            negated = _has_negation(title_lower, matched_mid_neg)
            if negated:
                sentiments.append(0.0)
                impact_scores.append(1)
            else:
                signal_counts["mid_neg"] += 1
                sentiments.append(-0.5)
                impact_scores.append(5)
                key_signals.append(matched_mid_neg)
        elif matched_pos_kw:
            negated = _has_negation(title_lower, matched_pos_kw)
            if negated:
                signal_counts["mid_neg"] += 1
                sentiments.append(-0.5)
                impact_scores.append(5)
                key_signals.append(f"[否定]{matched_pos_kw}")
            else:
                signal_counts["high_pos"] += 1
                sentiments.append(1.0)
                impact_scores.append(7)
                key_signals.append(matched_pos_kw)
        elif matched_mid_pos:
            negated = _has_negation(title_lower, matched_mid_pos)
            if negated:
                sentiments.append(0.0)
                impact_scores.append(1)
            else:
                signal_counts["mid_pos"] += 1
                sentiments.append(0.5)
                impact_scores.append(3)
                key_signals.append(matched_mid_pos)
        else:
            sentiments.append(0.0)
            impact_scores.append(1)

    sentiment_avg = sum(sentiments) / len(sentiments) if sentiments else 0.0
    impact_score = sum(impact_scores) / len(impact_scores) if impact_scores else 0.0
    neg_count = signal_counts["high_neg"] + signal_counts["mid_neg"]
    pos_count = signal_counts["high_pos"] + signal_counts["mid_pos"]

    if neg_count > pos_count * 1.5:
        momentum = "accelerating_negative"
    elif pos_count > neg_count * 1.5:
        momentum = "accelerating_positive"
    else:
        momentum = "stable"

    parts = []
    if st_signals:
        parts.append("重整信号：" + "；".join(st_signals[:2]))
    if dilution_warning:
        parts.append(dilution_warning)
    if entity_mismatches:
        parts.append(f"⚠️已过滤{len(entity_mismatches)}条同名关联公司新闻（避免误判）")
    if key_signals:
        parts.append(f"关键信号：{', '.join(set(key_signals[:3]))}")
    summary = "；".join(parts) if parts else "暂无重大信号"

    return {
        "sentiment_avg": round(sentiment_avg, 2),
        "signal_count": signal_counts,
        "key_signals": list(set(key_signals[:5])),
        "impact_score": round(impact_score, 1),
        "momentum": momentum,
        "summary": summary,
        "st_signals": st_signals,
        "dilution_warning": dilution_warning,
        "entity_mismatches": entity_mismatches,
    }


def _score_news(news: list) -> list:
    def score(n):
        t = n.get("title", "")
        tl = t.lower()
        if any(k in t for k in _KW_NOISE):
            return -1
        if any(k in t for k in _KW_HIGH_NEG) or any(k in tl for k in _KW_EN_HIGH_NEG):
            return 5
        if any(k in t for k in _KW_MID_NEG) or any(k in tl for k in _KW_EN_MID_NEG):
            return 4
        if any(k in t for k in _KW_HIGH_POS) or any(k in tl for k in _KW_EN_HIGH_POS):
            return 3
        if any(k in t for k in _KW_MID_POS) or any(k in tl for k in _KW_EN_MID_POS):
            return 2
        return 1

    def sentiment(n):
        score_val = score(n)
        if score_val in (5, 4):
            return -1.0
        if score_val in (3, 2):
            return 1.0
        return 0.0

    scored = [(score(n), n) for n in news if not n.get("entity_mismatch")]

    filtered = [(s, n) for s, n in scored if s > 0]
    filtered.sort(key=lambda x: x[0], reverse=True)

    # 批量写 sentiment 到 DB（单次连接，减少开销）
    updates = [{"s": sentiment(n), "nid": n.get("id")} for _, n in filtered if n.get("id")]
    if updates:
        import db
        try:
            with db.get_conn() as c:
                c.executemany("UPDATE stock_news SET sentiment=:s WHERE id=:nid", updates)
        except Exception:
            pass

    return [n for _, n in filtered]


# ── 前兆信号叉乘情境函数 ──────────────────────────────────────────────────────

def describe_margin_context(
    change_pct: float,
    price_change_pct: float,
    participation_vs_avg: float,
    participation_spike: bool,
    survey_count_30d: int,
    survey_avg_monthly: float,
) -> dict:
    """融券余量5档 × 价格方向 × 参与度飙升 × 调研，返回完整叙事情境。"""
    # 5档 tier
    if change_pct >= 50:
        tier = "heavy_short"
        base = "有人在大举押注这只股票会跌"
    elif change_pct >= 15:
        tier = "mild_short"
        base = "做空力量在温和增加"
    elif change_pct <= -50:
        tier = "heavy_cover"
        base = "做空者在加速离场"
    elif change_pct <= -15:
        tier = "mild_cover"
        base = "之前做空的人在减少赌注"
    else:
        return {
            "tier": "neutral", "base_desc": "做空方向没有明显变化",
            "price_context": "", "participation_context": "", "survey_context": "",
            "full_desc": "做空方向没有明显变化，该信号参考意义有限",
            "direction": "neutral", "signal_strength": 0,
        }

    # 价格方向
    if price_change_pct > 1:
        price_dir = "up"
    elif price_change_pct < -1:
        price_dir = "down"
    else:
        price_dir = "flat"

    _price_matrix = {
        ("heavy_short", "up"):   ("空头在逆势押跌——涨势若持续空头会被迫认亏（轧空风险）",   "mixed",   3),
        ("heavy_short", "down"): ("空头建仓成功，市场在跟着它们的方向走",                   "bearish",  3),
        ("heavy_short", "flat"): ("有人在悄悄建空仓，还没触发明显价格压力",                 "bearish",  2),
        ("mild_short",  "up"):   ("有做空力量，但涨势在压制它们",                           "mixed",    2),
        ("mild_short",  "down"): ("做空力量在增加，价格跟随下行",                           "bearish",  2),
        ("mild_short",  "flat"): ("做空在温和积累，方向待定",                               "bearish",  1),
        ("mild_cover",  "up"):   ("空头在撤退同时价格在涨——可能是被动止损",                 "bullish",  1),
        ("mild_cover",  "down"): ("空头主动获利了结，谨慎乐观",                             "bullish",  2),
        ("mild_cover",  "flat"): ("空头主动获利了结，谨慎乐观",                             "bullish",  2),
        ("heavy_cover", "up"):   ("空头加速离场 + 价格上涨——轧空可能正在发生",              "bullish",  3),
        ("heavy_cover", "down"): ("空头大举撤退，底部信号较可信",                           "bullish",  3),
        ("heavy_cover", "flat"): ("空头大举撤退，底部信号较可信",                           "bullish",  3),
    }
    price_ctx, direction, strength = _price_matrix.get(
        (tier, price_dir), ("方向待定", "neutral", 1)
    )

    # × 参与度飙升
    part_ctx = ""
    if participation_spike:
        _part_map = {
            ("heavy_short", "up"):   "轧空可能正在发生——大量机构涌入，空头承压",
            ("heavy_short", "down"): "机构在集中出货——空头和卖方联手，信号较强",
            ("heavy_short", "flat"): "机构大量交易但价格未动，博弈激烈",
            ("mild_short",  "up"):   "轧空可能正在发生——大量机构涌入，空头承压",
            ("mild_short",  "down"): "机构在集中出货——空头和卖方联手，信号较强",
            ("mild_short",  "flat"): "机构大量交易但价格未动，博弈激烈",
            ("mild_cover",  "up"):   "空头平仓 + 大量买盘，双向推涨，趋势较强",
            ("heavy_cover", "up"):   "空头平仓 + 大量买盘，双向推涨，趋势较强",
        }
        part_ctx = _part_map.get((tier, price_dir), "")
        if part_ctx and direction == "mixed":
            direction = "bullish" if price_dir == "up" else "bearish"

    # × 调研
    survey_ctx = ""
    has_survey = survey_count_30d > 0 and (
        survey_avg_monthly <= 0 or survey_count_30d > survey_avg_monthly * 1.3
    )
    if has_survey:
        if tier in ("heavy_short", "mild_short"):
            survey_ctx = "同期有机构来调研——内部可能有分歧，有人做空有人研究买"
        elif tier in ("mild_cover", "heavy_cover"):
            survey_ctx = "空头撤退 + 有机构调研，组合信号偏正面"

    parts = [base, price_ctx]
    if part_ctx:
        parts.append(part_ctx)
    if survey_ctx:
        parts.append(survey_ctx)
    full = "；".join(p for p in parts if p)

    return {
        "tier": tier,
        "base_desc": base,
        "price_context": price_ctx,
        "participation_context": part_ctx,
        "survey_context": survey_ctx,
        "full_desc": full,
        "direction": direction,
        "signal_strength": strength,
    }


def describe_survey_context(
    count_30d: int,
    avg_monthly: float,
    has_foreign: bool,
    repeat_institution: bool,
    margin_change_pct: float,
    participation_vs_avg: float,
) -> dict:
    """调研强度 × 外资/重复 × 融券方向 × 参与度，返回完整叙事情境。"""
    if avg_monthly <= 0:
        avg_monthly = 1.0

    ratio = count_30d / avg_monthly
    if count_30d == 0:
        intensity = "none"
        base = "近期无机构调研"
        direction = "neutral"
        strength = 0
    elif ratio >= 2.0:
        intensity = "surge"
        base = f"机构兴趣突然觉醒——近期密集调研，频率是平时的 {ratio:.1f} 倍"
        direction = "bullish"
        strength = 3
    elif ratio >= 1.3:
        intensity = "elevated"
        base = "机构关注度上升，调研比平时多"
        direction = "bullish"
        strength = 2
    elif ratio >= 0.7:
        intensity = "normal"
        base = "调研频率正常，无异常"
        direction = "neutral"
        strength = 0
    else:
        intensity = "declining"
        base = "机构关注度在下降，调研减少"
        direction = "bearish"
        strength = 1

    modifiers = []
    if has_foreign and intensity in ("surge", "elevated"):
        modifiers.append("其中有外资/头部私募（信息优势更强）")
    if repeat_institution and intensity in ("surge", "elevated"):
        modifiers.append("有机构多次拜访——可能在做深度尽调")
    if intensity in ("surge", "elevated"):
        if margin_change_pct <= -15:
            modifiers.append("空头同期撤退——调研热 + 做空减少，双重正面信号")
        elif margin_change_pct >= 15:
            modifiers.append("空头同期增加——内部有分歧，有人调研有人做空")
            direction = "mixed"
        if participation_vs_avg > 10:
            modifiers.append("机构不只在看，参与度也在上升——可能已在建仓")
    if intensity in ("declining", "none"):
        modifiers.append("机构注意力转移，关注度下滑")

    full = base
    if modifiers:
        full += "；" + "；".join(modifiers[:3])

    return {
        "intensity": intensity,
        "base_desc": base,
        "modifiers": modifiers,
        "full_desc": full,
        "direction": direction,
        "signal_strength": strength,
    }


def describe_participation_context(
    latest: float,
    avg_30d: float,
    trend: str,
    spike: bool,
    price_change_pct: float,
    margin_change_pct: float,
) -> dict:
    """机构参与度趋势 × 价格方向 × 融券状态，返回完整叙事情境。"""
    if price_change_pct > 1:
        price_dir = "up"
    elif price_change_pct < -1:
        price_dir = "down"
    else:
        price_dir = "flat"

    heavy_short = margin_change_pct >= 15

    if spike:
        if price_dir == "up":
            desc = "今天机构交易异常活跃，价格上涨——有机构在主动买入"
            direction = "bullish"
            strength = 3
        elif price_dir == "down":
            desc = "今天机构交易异常活跃，价格下跌——有机构在出货"
            direction = "bearish"
            strength = 3
        elif heavy_short:
            desc = "机构大量交易但价格未动，融券也在增加——博弈激烈"
            direction = "mixed"
            strength = 2
        else:
            desc = "机构大量交易但价格未动，方向待定"
            direction = "mixed"
            strength = 2
    elif trend == "上升":
        if price_dir == "up":
            desc = "机构越来越关注，并跟随上涨，趋势有支撑"
            direction = "bullish"
            strength = 2
        elif price_dir == "down":
            desc = "机构活跃度上升但价格在跌，可能有分歧"
            direction = "mixed"
            strength = 1
        else:
            desc = "机构在悄悄布局，还未触发价格变化"
            direction = "bullish"
            strength = 1
    elif trend == "下降":
        desc = "机构在减少操作，关注度下滑"
        direction = "bearish"
        strength = 1
    else:
        desc = "机构参与度平稳，没有异常波动"
        direction = "neutral"
        strength = 0

    return {
        "full_desc": desc,
        "direction": direction,
        "signal_strength": strength,
        "spike": spike,
        "trend": trend,
        "price_dir": price_dir,
    }


def label_news_vs_institution(sentiment: str, inst_direction: str) -> str:
    """每条新闻与当前机构意向的一致性标注。
    Returns: 'consistent' | 'divergent' | 'contrarian' | 'none'
    """
    if not inst_direction or inst_direction == "neutral":
        return "none"
    matrix = {
        ("positive", "bullish"): "consistent",
        ("positive", "bearish"): "divergent",
        ("negative", "bullish"): "contrarian",
        ("negative", "bearish"): "consistent",
    }
    return matrix.get((sentiment, inst_direction), "none")


def prophet_daily_score(participation: dict, survey_inst_today: int = 0) -> dict:
    """一天的机构脚印增量——供预言家线累积（US-75）。正=机构在进，负=在退。
    只有"当日真·观测"进累积：① 参与度 z 分（当日相对 30 日均值的偏离）
    ② 当天实际发生的调研加成（按 event 日期匹配，不是快照里的滚动窗口）。
    融券是 30 日滚动值、无法归因到某一天，不进累积（留在层3情境卡）。
    纯规则。Returns: {value, event_inst, spike}
    """
    participation = participation or {}
    p = 0.0
    latest = participation.get("latest")
    avg = participation.get("avg_30d")
    sd = participation.get("stdev") or 0
    if latest is not None and avg is not None and sd > 0:
        p = max(-2.0, min(2.0, (latest - avg) / sd))

    survey_inst_today = int(survey_inst_today or 0)
    bump = min(1.5, 0.3 * survey_inst_today) if survey_inst_today > 0 else 0.0

    return {
        "value": round(p + bump, 3),
        "event_inst": survey_inst_today,
        "spike": bool(participation.get("spike")),
    }
