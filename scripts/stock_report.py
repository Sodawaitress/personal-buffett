"""Report and push-content builders extracted from stock_pipeline."""

from datetime import datetime, timedelta

import db as _db
from scripts.config import BUFFETT_PROFILES, CN_TZ, NEGATIVE_SIGNALS, NOISE_KEYWORDS, POSITIVE_SIGNALS

def generate_report(data: dict, ai_analysis: dict = None,
                    allowed_codes: set = None) -> str:
    """
    生成 Markdown 报告。
    allowed_codes: 若指定，只显示该集合内的股票；None = 今日有行情或新闻的全部股票。
    """
    date      = data["date"]
    quotes    = data.get("quotes", {})
    news      = data.get("news", {})
    ann       = data.get("announcements", {})
    insider   = data.get("insider", {})
    fund_flow = data.get("fund_flow", {})
    nb        = data.get("north_bound", {})
    lhb       = data.get("lhb", [])
    sector    = data.get("sector_news", [])
    intl      = data.get("intl_news", {})
    macro     = data.get("macro", {})
    rbnz      = data.get("rbnz", [])
    nzx_ann   = data.get("nzx_announcements", {})
    nzx_earn  = data.get("nzx_earnings", [])
    cn_earn   = data.get("cn_earnings", [])

    # ── 涨跌排序 ──────────────────────────────────────
    sorted_stocks = sorted(
        quotes.values(),
        key=lambda x: x.get("change", 0),
        reverse=True
    )

    def pct_bar(pct):
        if pct >= 5:   return "🔴🔴"
        if pct >= 2:   return "🔴"
        if pct >= 0:   return "🟠"
        if pct >= -2:  return "🟡"
        if pct >= -5:  return "🟢"
        return "🟢🟢"

    # ── 行情汇总表 ─────────────────────────────────────
    quote_lines = []
    for q in sorted_stocks:
        bar   = pct_bar(q["change"])
        sign  = "+" if q["change"] >= 0 else ""
        quote_lines.append(
            f"| {q['name']}({q['code']}) | ¥{q['price']:.2f} | "
            f"{sign}{q['change']:.2f}% {bar} | {q['amount']:.1f}亿 |"
        )

    # ── 北向资金 ───────────────────────────────────────
    nb_line = ""
    if nb:
        sign = "净流入 📈" if nb.get("total_net", 0) >= 0 else "净流出 📉"
        nb_line = f"**北向资金**：{nb.get('total_net', 0):.2f}亿元 {sign}（沪股通 {nb.get('sh_net',0):.1f}亿 · 深股通 {nb.get('sz_net',0):.1f}亿）"

    # ── 龙虎榜预警 ─────────────────────────────────────
    lhb_section = ""
    if lhb:
        lhb_lines = []
        for h in lhb:
            lhb_lines.append(f"- **{h['name']}**：{h['reason']}｜买入 {h['buy']:.1f}亿 卖出 {h['sell']:.1f}亿")
        lhb_section = "\n## 🔔 龙虎榜预警\n\n" + "\n".join(lhb_lines) + "\n"

    # ── 个股动态（巴菲特视角）─────────────────────────
    def classify_news(title: str):
        """判断新闻信号方向"""
        if any(k in title for k in NOISE_KEYWORDS):
            return "noise"
        if any(k in title for k in NEGATIVE_SIGNALS):
            return "negative"
        if any(k in title for k in POSITIVE_SIGNALS):
            return "positive"
        return "neutral"

    # ── 有效自选股列表 ─────────────────────────────────
    # 优先用 allowed_codes（per-user push），否则从今日数据动态推导
    if allowed_codes is not None:
        active_codes = allowed_codes
    else:
        # 今天有新闻 OR 有行情的股票 = 今日有动静的
        active_codes = set(news.keys()) | set(quotes.keys())

    eff_watchlist = [
        (quotes.get(c, {}).get("name", c), c, "")
        for c in sorted(active_codes)
        if c in quotes or c in news
    ]
    sorted_stocks = [q for q in sorted_stocks if q["code"] in active_codes]

    stock_sections = []
    for name, code, desc in eff_watchlist:
        stock_news = news.get(code, [])
        stock_ann  = ann.get(code, [])
        q          = quotes.get(code, {})
        profile    = BUFFETT_PROFILES.get(code, {})

        # 过滤噪音新闻
        real_news = [n for n in stock_news if classify_news(n["title"]) != "noise"]
        if not real_news and not stock_ann:
            continue

        price_line = ""
        if q:
            sign = "+" if q["change"] >= 0 else ""
            price_line = f" · ¥{q['price']:.2f}（{sign}{q['change']:.2f}%）"

        grade_emoji = profile.get("grade_emoji", "")
        grade       = profile.get("grade", "")
        lines = [f"### {grade_emoji} {name}（{code}）{price_line}  [{grade}级]"]

        # 巴菲特底色提示
        if profile:
            lines.append(f"> 护城河：{profile['moat']}")
            lines.append(f"> ROE：{profile['roe_5y']}  |  关注：{'、'.join(profile.get('watch', []))}")

        # 🤖 AI 巴菲特分析
        ai_text = (ai_analysis or {}).get(code, "")
        if ai_text:
            lines.append(f"> 🤖 **巴菲特分析**：{ai_text}")

        lines.append("")  # 空行

        # 主力资金流向
        ff = fund_flow.get(code, {})
        net = ff.get("main_net", 0) if ff else None
        if ff:
            ratio = ff.get("main_ratio", 0)
            direction = "📈 净流入" if net >= 0 else "📉 净流出"
            lines.append(f"> 主力资金：{direction} **{abs(net):.2f}亿**（占比{ratio:.1f}%）")

        # 信号分歧检测：AI看多 但机构在流出
        ai_bullish = any(k in ai_text for k in ["买入", "博弈介入", "适合定投", "适合一次性买入"])
        ai_bearish = any(k in ai_text for k in ["减仓", "卖出", "坚决回避"])
        if ai_text and net is not None:
            if ai_bullish and net < -0.5:
                lines.append(f"> ⚠️ **信号分歧**：基本面看多，但主力今日净流出 {abs(net):.2f}亿——好消息可能已price in，建议观望等回调")

        # 估值地板检测：大跌 + 历史低估值 → 利空可能已price in
        current_price = q.get("price")
        if current_price and ai_text:
            fund_data  = _db.get_fundamentals(code)
            price_hist = _db.get_price_history(code, days=90)
            if price_hist:
                oldest_price = price_hist[-1].get("price")
                if oldest_price and oldest_price > 0:
                    drop_90d = (current_price - oldest_price) / oldest_price * 100
                    pb_pct   = fund_data.get("pb_percentile_5y")
                    pe_pct   = fund_data.get("pe_percentile_5y")
                    oversold = drop_90d < -25
                    at_floor = (pb_pct is not None and pb_pct < 20) or \
                               (pe_pct is not None and pe_pct < 20)
                    if oversold and at_floor:
                        floor_parts = []
                        if pb_pct is not None and pb_pct < 20:
                            floor_parts.append(f"PB处于5年{pb_pct:.0f}%低位")
                        if pe_pct is not None and pe_pct < 20:
                            floor_parts.append(f"PE处于5年{pe_pct:.0f}%低位")
                        label = "⚠️ 减仓信号存疑" if ai_bearish else "🛡️ 安全边际出现"
                        lines.append(
                            f"> {label}：近90天跌幅{drop_90d:.1f}%，"
                            f"{' | '.join(floor_parts)}"
                            f"——利空可能已price in，建议观望而非割肉"
                        )

        # 大股东增减持
        ins = insider.get(code, [])
        for i in ins[:2]:
            badge = "✅" if "增持" in i["type"] or "买入" in i["type"] else "⚠️"
            lines.append(f"> {badge} 股东变动：{i['holder']} **{i['type']}** {i['ratio']} （{i['date']}）")

        lines.append("")

        # 公告优先（公告比新闻重要）
        for a in stock_ann[:2]:
            lines.append(f"📋 **[{a['title'][:60]}]({a['link']})** {a['date']}")

        # 实质性新闻 + 信号标注
        for item in real_news[:3]:
            sig   = classify_news(item["title"])
            badge = {"positive": "✅ ", "negative": "⚠️ ", "neutral": ""}.get(sig, "")
            link  = item.get("link", "")
            title = item["title"][:70]
            src   = f"（{item['source']}·{item['time'][:10]}）"
            if link:
                lines.append(f"- {badge}[{title}]({link}){src}")
            else:
                lines.append(f"- {badge}{title}{src}")

        stock_sections.append("\n".join(lines))

    # ── 国际资讯 ──────────────────────────────────────
    intl_lines = []
    # 个股相关
    for name, code, _ in eff_watchlist:
        for item in intl.get(code, [])[:2]:
            intl_lines.append(
                f"- 🌐 **[{item['title'][:80]}]({item['link']})**"
                f"（{item['source']}）*{item['label']}*"
            )
    # 板块宏观
    for item in intl.get("_sector", [])[:4]:
        intl_lines.append(
            f"- 🌍 **[{item['title'][:80]}]({item['link']})**"
            f"（{item['source']}）*{item['label']}*"
        )

    # ── 板块快讯 ───────────────────────────────────────
    sector_lines = []
    for s in sector[:8]:
        link = s.get("link", "")
        t    = s["title"][:80]
        tm   = s["time"][11:16] if len(s["time"]) > 10 else ""
        if link:
            sector_lines.append(f"- [{t}]({link}) {tm}")
        else:
            sector_lines.append(f"- {t} {tm}")

    # ── 巴菲特总评（快速扫描）────────────────────────
    alert_lines = []
    for name, code, _ in eff_watchlist:
        p = BUFFETT_PROFILES.get(code, {})
        q = quotes.get(code, {})
        stock_news = news.get(code, [])
        # 今日是否有负面信号
        neg_today = [n["title"][:50] for n in stock_news
                     if classify_news(n["title"]) == "negative"]
        grade = p.get("grade", "?")
        g_e   = p.get("grade_emoji", "")
        if q:
            sign = "+" if q["change"] >= 0 else ""
            price_str = f"¥{q['price']:.2f}（{sign}{q['change']:.2f}%）"
        else:
            price_str = "—"
        row = f"| {g_e} {name} | {grade} | {price_str} | {p.get('moat','—')[:30]} |"
        if neg_today:
            row += f" ⚠️ {neg_today[0]}"
        alert_lines.append(row)

    buffett_summary = """## 🔍 巴菲特评级一览

| 股票 | 评级 | 现价 | 护城河 |
|---|---|---|---|
""" + "\n".join(alert_lines)

    # ── 宏观环境 ──────────────────────────────────────
    macro_lines = []

    # A股三大指数
    indices = macro.get("cn_indices", {})
    if indices:
        idx_parts = []
        for key in ("sh", "sz", "cyb"):
            idx = indices.get(key, {})
            if idx:
                arrow = "📈" if idx["change"] >= 0 else "📉"
                idx_parts.append(f"{idx['name']} {idx['price']:.2f}（{idx['change']:+.2f}%）{arrow}")
        if idx_parts:
            macro_lines.append("**A股指数**：" + " | ".join(idx_parts))

    # CNY/USD 汇率
    cny = macro.get("cny_usd", {})
    if cny:
        macro_lines.append(f"**USD/CNY**：{cny['rate']} {cny.get('direction','')}")

    # 大宗商品
    comm = macro.get("commodities", {})
    if comm:
        comm_parts = []
        for v in comm.values():
            arrow = "📈" if v["change"] >= 0 else "📉"
            comm_parts.append(f"{v['name']} {v['price']:.0f}（{v['change']:+.2f}%）{arrow}")
        if comm_parts:
            macro_lines.append("**大宗商品**：" + " | ".join(comm_parts))

    # Fear & Greed
    fg = macro.get("fear_greed", {})
    if fg:
        macro_lines.append(f"**市场情绪**：Fear & Greed {fg['score']}/100 — {fg['buffett']}")

    # 挖掘机销量
    excav = macro.get("excavator", {})
    excav_news = excav.get("latest_news", [])
    if excav_news:
        macro_lines.append(f"**🚜 挖掘机先行指标**：{excav_news[0]['title'][:80]}")

    macro_section = ""
    if macro_lines:
        macro_section = "## 🌍 宏观环境\n\n" + "\n\n".join(macro_lines) + "\n"

    # ── 近期重要日程 ──────────────────────────────────
    calendar_lines = []

    # FOMC
    fomc = macro.get("fomc", [])
    for f in fomc[:2]:
        calendar_lines.append(f"- 🏦 **[{f['title'][:70]}]({f['link']})** （Fed · {f['time'][:10]}）")

    # RBNZ
    for r in rbnz[:2]:
        calendar_lines.append(f"- 🇳🇿 **[{r['title'][:70]}]({r['link']})** （RBNZ · {r['time'][:10]}）")

    # A股财报日历
    for e in cn_earn[:4]:
        calendar_lines.append(f"- 📋 **{e['name']}**（{e['code']}）预计披露 {e['date']} {e['type']}")

    # NZX财报日历
    for e in nzx_earn[:3]:
        calendar_lines.append(f"- 📋 **{e['name']}**（{e['ticker']}）财报约 {e['date']}")

    calendar_section = ""
    if calendar_lines:
        calendar_section = "## 📅 重要日程\n\n" + "\n".join(calendar_lines) + "\n"

    # ── NZX公司公告 ───────────────────────────────────
    nzx_ann_lines = []
    for ticker, items in nzx_ann.items():
        profile = {}
        try:
            from nz_profiles import NZ_PROFILES
            profile = NZ_PROFILES.get(ticker, {})
        except Exception:
            pass
        name = profile.get("name", ticker)
        for item in items:
            nzx_ann_lines.append(
                f"- **{name}** [{item['title'][:70]}]({item['link']}) ({item['source']} · {item['time']})"
            )

    nzx_section = ""
    if nzx_ann_lines:
        nzx_section = "## 🇳🇿 NZX公司公告\n\n" + "\n".join(nzx_ann_lines) + "\n"

    report = f"""# 📈 自选股日报 {date}

{buffett_summary}

{macro_section}
## 📊 今日行情

| 股票 | 现价 | 涨跌幅 | 成交额 |
|---|---|---|---|
""" + "\n".join(quote_lines) + f"""

{nb_line}
{lhb_section}
## 📰 个股动态（巴菲特视角）

""" + "\n\n".join(stock_sections) + f"""

{nzx_section}
## 🌐 国际视角

""" + "\n".join(intl_lines) + """

## 🗞️ 板块·政策快讯

""" + "\n".join(sector_lines) + f"""

{calendar_section}
---
*数据来源：新浪财经·东方财富·财联社·RBNZ·Federal Reserve · {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M CST')}*
*评级说明：A=优质护城河 B=合格 C=周期/弱护城河 D=警报*
"""
    return report.strip()



def _get_buy_watching(user_id: int) -> list:
    """
    返回某用户 watching 股票中，建议买入的代码列表。
    条件：grade 在 (A, B+) 或 conclusion == '买入'
    """
    watching = _db.get_user_watching(user_id)
    result = []
    for code in watching:
        a = _db.get_latest_analysis(code)
        if not a:
            continue
        grade      = a.get("grade", "")
        conclusion = a.get("conclusion", "")
        if grade in ("A", "B+") or conclusion == "买入":
            result.append(code)
    return result


def _stock_price_str(code: str, quotes: dict) -> tuple:
    """
    返回 (name, price_str, change_str)。
    优先从 data quotes 读，没有就从 DB 最新价格读。
    """
    q = quotes.get(code, {})
    name   = q.get("name") or code
    price  = q.get("price")
    change = q.get("change")

    if price is None:
        # 回退到 DB
        p = _db.get_latest_price(code)
        if p:
            price  = p.get("price")
            change = p.get("change_pct")
            stock  = _db.get_stock(code)
            name   = (stock or {}).get("name", code) if stock else code

    price_s  = f"¥{price:.2f}" if price is not None else "—"
    change_s = (("+" if (change or 0) >= 0 else "") + f"{change:.2f}%") if change is not None else "—"
    return name, price_s, change_s


def _score_report(code: str) -> int:
    """
    US-59：推送质量评分（0-100）。
    低于 40 分的分析不推送（防止把空分析 / LLM 失败结果推给用户）。
    评分规则：
      - 有分析记录:            +20 分（基础）
      - grade 字段非空非"—":  +20 分
      - conclusion 有实际内容: +20 分
      - reasoning >= 30 字:   +20 分
      - 分析日期在今天或昨天:  +20 分
    """
    a = _db.get_latest_analysis(code)
    if not a:
        return 0

    score = 20  # 有记录即 +20

    grade = (a.get("grade") or "").strip()
    if grade and grade != "—":
        score += 20

    conclusion = (a.get("conclusion") or "").strip()
    if conclusion and conclusion != "—":
        score += 20

    reasoning = (a.get("reasoning") or a.get("letter_html") or "").strip()
    if len(reasoning) >= 30:
        score += 20

    analysis_date = (a.get("analysis_date") or "")
    today     = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    yesterday = (datetime.now(CN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    if analysis_date in (today, yesterday):
        score += 20

    return score


PUSH_QUALITY_THRESHOLD = 40   # 低于此分不推送


def _stock_card(code: str, quotes: dict, news_data: dict) -> str:
    """
    为单只股票生成推送卡片：名称 + 价格 + 评级 + 分析摘要 + 最多2条新闻。
    """
    name, price_s, change_s = _stock_price_str(code, quotes)
    a = _db.get_latest_analysis(code)

    grade      = a.get("grade", "—") if a else "—"
    conclusion = a.get("conclusion", "—") if a else "—"
    reasoning  = ""
    if a:
        reasoning = (a.get("reasoning") or a.get("letter_html") or "").strip()
        # 取第一句（到第一个句号/换行）
        for sep in ("。", "\n", ".", "；"):
            idx = reasoning.find(sep)
            if 0 < idx < 120:
                reasoning = reasoning[:idx + 1]
                break
        else:
            reasoning = reasoning[:100]

    lines = [f"**{name}（{code}）** {price_s} {change_s} | {grade} · {conclusion}"]
    if reasoning:
        lines.append(f"> {reasoning}")

    # 最多 2 条新闻（优先从 data，没有则从 DB）
    stock_news = news_data.get(code, [])
    if not stock_news:
        stock_news = _db.get_stock_news(code, days=3)
    for n in stock_news[:2]:
        title = (n.get("title") or "")[:60]
        if title:
            lines.append(f"- {title}")

    return "\n".join(lines)


def build_user_push_content(user_id: int, data: dict, ai_analysis: dict,
                             date_str: str) -> str:
    """
    为某用户生成微信推送内容。
    - 持仓股：每只一张卡片（价格 + 评级 + 分析摘要 + 最多2条新闻）
    - 关注股中建议买入（A/B+/结论买入）：另起一节
    任何用户均可使用，无硬编码。
    """
    quotes    = data.get("quotes", {})
    news_data = data.get("news", {})
    holdings  = _db.get_user_holdings(user_id)
    buy_watch = _get_buy_watching(user_id)

    sections = []

    if holdings:
        cards = []
        for c in holdings:
            score = _score_report(c)
            if score >= PUSH_QUALITY_THRESHOLD:
                cards.append(_stock_card(c, quotes, news_data))
            else:
                print(f"    ⚠️ {c} 质量评分 {score}/100，跳过推送")
        if cards:
            sections.append("## 📊 今日持仓\n\n" + "\n\n".join(cards))

    if buy_watch:
        cards = []
        for c in buy_watch:
            score = _score_report(c)
            if score >= PUSH_QUALITY_THRESHOLD:
                cards.append(_stock_card(c, quotes, news_data))
            else:
                print(f"    ⚠️ {c} 质量评分 {score}/100，跳过推送")
        if cards:
            sections.append("## ⭐ 建议关注（评级买入）\n\n" + "\n\n".join(cards))

    if not sections:
        return ""

    header = f"**股票日报 {date_str}**\n持仓 {len(holdings)} 只 · 买入候选 {len(buy_watch)} 只\n"
    return header + "\n\n---\n\n".join(sections)

