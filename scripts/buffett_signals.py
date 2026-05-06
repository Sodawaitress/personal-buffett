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
    updates = [(sentiment(n), n.get("id")) for s, n in filtered if n.get("id")]
    if updates:
        import db
        try:
            with db.get_conn() as c:
                c.executemany("UPDATE stock_news SET sentiment=? WHERE id=?", updates)
        except Exception:
            pass

    return [n for _, n in filtered]
