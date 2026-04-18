def _analyze_news_signals(news: list) -> dict:
    HIGH_NEG = ["辞职", "离职", "被查", "立案", "违规", "处罚", "诉讼", "商誉减值", "暴雷"]
    MID_NEG = ["减持", "亏损", "下滑", "下降", "降级", "失败", "撤回", "退出"]
    HIGH_POS = ["回购", "增持", "大额分红", "创历史新高", "重大中标", "获批上市"]
    MID_POS = ["派息", "分红", "签约", "战略合作", "净利润增长", "获批", "中标"]
    NOISE = ["只个股", "家公司", "突破年线", "牛熊分界", "资金流向日报", "盘中播报", "技术分析", "K线", "涨跌幅排名"]

    EN_HIGH_NEG = [
        "resign",
        "fired",
        "scandal",
        "lawsuit",
        "fraud",
        "downgrade",
        "investigation",
        "bankruptcy",
        "loss",
        "crisis",
        "collapse",
    ]
    EN_MID_NEG = ["decline", "miss", "lower", "reduce", "weak", "challenge", "concern"]
    EN_HIGH_POS = ["upgrade", "acquisition", "record profit", "breakthrough", "approval", "deal", "expansion", "beat estimate"]
    EN_MID_POS = ["partnership", "growth", "earnings", "profit", "revenue"]

    signal_counts = {"high_neg": 0, "mid_neg": 0, "high_pos": 0, "mid_pos": 0}
    sentiments = []
    key_signals = []
    impact_scores = []

    for n in news:
        title = n.get("title", "").lower()
        if any(k in title for k in NOISE):
            continue

        if any(k in title for k in HIGH_NEG) or any(k in title for k in EN_HIGH_NEG):
            signal_counts["high_neg"] += 1
            sentiments.append(-1.0)
            impact_scores.append(8)
            key_signals.append(
                next((k for k in HIGH_NEG if k in title), next((k for k in EN_HIGH_NEG if k in title), "负面信号"))
            )
        elif any(k in title for k in MID_NEG) or any(k in title for k in EN_MID_NEG):
            signal_counts["mid_neg"] += 1
            sentiments.append(-0.5)
            impact_scores.append(5)
            key_signals.append(
                next((k for k in MID_NEG if k in title), next((k for k in EN_MID_NEG if k in title), "中性负面"))
            )
        elif any(k in title for k in HIGH_POS) or any(k in title for k in EN_HIGH_POS):
            signal_counts["high_pos"] += 1
            sentiments.append(1.0)
            impact_scores.append(7)
            key_signals.append(
                next((k for k in HIGH_POS if k in title), next((k for k in EN_HIGH_POS if k in title), "正面信号"))
            )
        elif any(k in title for k in MID_POS) or any(k in title for k in EN_MID_POS):
            signal_counts["mid_pos"] += 1
            sentiments.append(0.5)
            impact_scores.append(3)
            key_signals.append(
                next((k for k in MID_POS if k in title), next((k for k in EN_MID_POS if k in title), "中性正面"))
            )
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

    if key_signals:
        summary = f"最近关键信号：{', '.join(set(key_signals[:3]))}"
    else:
        summary = "暂无重大信号"

    return {
        "sentiment_avg": round(sentiment_avg, 2),
        "signal_count": signal_counts,
        "key_signals": list(set(key_signals[:5])),
        "impact_score": round(impact_score, 1),
        "momentum": momentum,
        "summary": summary,
    }


def _score_news(news: list) -> list:
    HIGH_NEG = ["辞职", "离职", "被查", "立案", "违规", "处罚", "诉讼", "商誉减值", "暴雷"]
    MID_NEG = ["减持", "亏损", "下滑", "下降", "降级", "失败", "撤回", "退出"]
    HIGH_POS = ["回购", "增持", "大额分红", "创历史新高", "重大中标", "获批上市"]
    MID_POS = ["派息", "分红", "签约", "战略合作", "净利润增长", "获批", "中标"]
    NOISE = ["只个股", "家公司", "突破年线", "牛熊分界", "资金流向日报", "盘中播报", "技术分析", "K线", "涨跌幅排名"]

    def score(n):
        t = n.get("title", "")
        if any(k in t for k in NOISE):
            return -1
        if any(k in t for k in HIGH_NEG):
            return 5
        if any(k in t for k in MID_NEG):
            return 4
        if any(k in t for k in HIGH_POS):
            return 3
        if any(k in t for k in MID_POS):
            return 2
        return 1

    def sentiment(n):
        score_val = score(n)
        if score_val in (5, 4):
            return -1.0
        if score_val in (3, 2):
            return 1.0
        return 0.0

    scored = [(score(n), n) for n in news]

    import db

    for s, n in scored:
        if s > 0:
            n_sentiment = sentiment(n)
            try:
                with db.get_conn() as c:
                    c.execute("UPDATE stock_news SET sentiment=? WHERE id=?", (n_sentiment, n.get("id")))
            except Exception:
                pass

    filtered = [(s, n) for s, n in scored if s > 0]
    filtered.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in filtered]
