#!/usr/bin/env python3
"""
股票雷达 · 全流程 Pipeline
每日 8:30 自动运行：抓取 → 生成报告 → 推送 Discord
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # stock-radar root for db

import json, subprocess, ssl, time, urllib.request
from datetime import datetime
import db as _db
from config import (
    WATCHLIST, HK_WATCHLIST, RAW_OUTPUT, REPORT_OUTPUT,
    DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, CN_TZ,
    BUFFETT_PROFILES, POSITIVE_SIGNALS, NEGATIVE_SIGNALS, NOISE_KEYWORDS,
    SERVERCHAN_KEY
)
from buffett_analyst import analyze_all
from macro_fetch import fetch_all_macro
from nz_fetch import fetch_rbnz_news, fetch_nzx_announcements, fetch_nzx_earnings_calendar
from stock_fetch import fetch_cn_earnings_calendar


# ── 运行抓取 ──────────────────────────────────────────
def run_fetch():
    script = os.path.join(os.path.dirname(__file__), "stock_fetch.py")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"⚠️ {result.stderr[:300]}")


# ── 生成报告 ──────────────────────────────────────────
def generate_report(data: dict, ai_analysis: dict = None,
                    allowed_codes: set = None) -> str:
    """
    生成 Markdown 报告。
    allowed_codes: 若指定，只显示该集合内的股票；None = 全部（WATCHLIST）。
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
    # allowed_codes=None → 全部（admin pipeline 默认行为）
    # allowed_codes=set  → 只显示指定代码（per-user push）
    if allowed_codes is None:
        eff_watchlist = WATCHLIST
    else:
        # 从已抓取数据中重建 (name, code, desc) 元组
        eff_watchlist = [
            (quotes.get(c, {}).get("name", c), c, "")
            for c in allowed_codes
        ]
        # 行情表也只显示这些代码
        sorted_stocks = [q for q in sorted_stocks if q["code"] in allowed_codes]

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
        if ai_analysis and code in ai_analysis:
            lines.append(f"> 🤖 **巴菲特分析**：{ai_analysis[code]}")

        lines.append("")  # 空行

        # 主力资金流向
        ff = fund_flow.get(code, {})
        if ff:
            net = ff.get("main_net", 0)
            ratio = ff.get("main_ratio", 0)
            direction = "📈 净流入" if net >= 0 else "📉 净流出"
            lines.append(f"> 主力资金：{direction} **{abs(net):.2f}亿**（占比{ratio:.1f}%）")

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


# ── Discord 推送 ──────────────────────────────────────
def send_discord_chunks(content: str):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    url     = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type":  "application/json",
        "User-Agent":    "DiscordBot (https://github.com, 1.0)"
    }
    # 按 ## 分节
    sections  = content.split("\n## ")
    chunks, current = [], sections[0]
    for sec in sections[1:]:
        candidate = current + "\n## " + sec
        if len(candidate) <= 1900:
            current = candidate
        else:
            chunks.append(current)
            current = "## " + sec
    chunks.append(current)

    sent = 0
    for chunk in chunks:
        payload = json.dumps({"content": chunk[:1990]}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                if r.status == 200:
                    sent += 1
        except Exception as e:
            print(f"  ⚠️ Discord: {e}")
        time.sleep(0.5)

    print(f"📨 Discord 发送：{sent}/{len(chunks)} 块")


# ── Server酱 推送（支持指定 key）─────────────────────
def send_serverchan(key: str, title: str, content: str):
    """推送到 Server酱。key 为 SCT 开头的 sendkey。"""
    if not key:
        print("  ⚠️ Server酱 key 为空，跳过")
        return
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    # Server酱 desp 限 64KB，按 4000 字切块顺序发送
    chunks = [content[i:i+4000] for i in range(0, len(content), 4000)] or [""]
    for i, chunk in enumerate(chunks):
        chunk_title = title if i == 0 else f"{title}（续{i}）"
        payload = json.dumps({"title": chunk_title, "desp": chunk}).encode()
        url = f"https://sctapi.ftqq.com/{key}.send"
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                resp = json.loads(r.read().decode())
                if resp.get("data", {}).get("errno") == 0:
                    print(f"  📱 Server酱 [{i+1}/{len(chunks)}] 成功")
                else:
                    print(f"  📱 Server酱 返回: {resp}")
        except Exception as e:
            print(f"  ⚠️ Server酱: {e}")
        time.sleep(0.3)


def _get_a_grade_watching(user_id: int, date_str: str) -> list:
    """返回某用户 watching 股票中，今日分析评级为 A 的代码列表。"""
    watching = _db.get_user_watching(user_id)
    if not watching:
        return []
    result = []
    for code in watching:
        a = _db.get_latest_analysis(code)
        if a and a.get("grade") == "A" and a.get("analysis_date", "") >= date_str:
            result.append(code)
    return result


def build_user_push_content(user_id: int, data: dict, ai_analysis: dict,
                             date_str: str) -> str:
    """
    为某用户生成微信推送内容（紧凑格式）：
    - 持仓表格 + 巴菲特一句话（如有持仓）
    - 今日 A 级观察股（如有）
    """
    quotes     = data.get("quotes", {})
    holdings   = _db.get_user_holdings(user_id)
    a_watching = _get_a_grade_watching(user_id, date_str)

    sections = []

    if holdings:
        rows = ["## 今日持仓\n",
                "| 股票 | 现价 | 涨跌 | 评级 |",
                "|------|------|------|------|"]
        buffett_lines = []
        news_lines = []
        for code in holdings:
            q = quotes.get(code, {})
            a = _db.get_latest_analysis(code)
            name = q.get("name", code)
            price = q.get("price")
            change = q.get("change")
            grade  = a.get("grade", "—") if a else "—"
            price_s  = f"¥{price:.2f}" if price is not None else "—"
            change_s = (("+" if change >= 0 else "") + f"{change:.2f}%") if change is not None else "—"
            rows.append(f"| {name}（{code}） | {price_s} | {change_s} | {grade} |")
            if a:
                # 用 reasoning 做摘要（比 conclusion 一个字有内容得多）
                reasoning = (a.get("reasoning") or a.get("letter_html") or "").strip()
                if reasoning:
                    buffett_lines.append(f"**{name}**（{grade}）\n{reasoning[:150]}……")
            # 今日新闻：取最新 1 条标题
            stock_news = data.get("news", {}).get(code, [])
            if stock_news:
                top = stock_news[0]
                news_lines.append(f"- **{name}**：{top.get('title', '')[:60]}")
        sections.append("\n".join(rows))
        if buffett_lines:
            sections.append("### 🧠 巴菲特分析\n\n" + "\n\n---\n\n".join(buffett_lines))
        if news_lines:
            sections.append("### 📰 今日要闻\n\n" + "\n".join(news_lines))

    if a_watching:
        lines = ["## ⭐ 今日 A 级关注股（建议留意）\n"]
        for code in a_watching:
            a = _db.get_latest_analysis(code)
            q = quotes.get(code, {})
            name = q.get("name", code)
            price = q.get("price")
            change = q.get("change")
            price_str = ""
            if price is not None:
                sign = "+" if (change or 0) >= 0 else ""
                change_str = f"{sign}{change:.2f}%" if change is not None else ""
                price_str = f" · ¥{price:.2f}（{change_str}）"
            conclusion = (a.get("conclusion") or "")[:80] if a else ""
            lines.append(f"- **{name}（{code}）**{price_str}")
            if conclusion:
                lines.append(f"  > {conclusion}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n---\n\n".join(sections)


# ── Server酱 微信推送 ─────────────────────────────────
def send_wechat(title: str, content: str):
    """通过 Server酱 推送到微信"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    url     = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
    payload = json.dumps({"title": title, "desp": content}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            resp = json.loads(r.read().decode())
            if resp.get("data", {}).get("errno") == 0:
                print(f"📱 微信推送成功")
            else:
                print(f"📱 微信推送返回: {resp}")
    except Exception as e:
        print(f"  ⚠️ 微信: {e}")


# ── Bear 存档 ─────────────────────────────────────────
def save_to_bear(title: str, content: str):
    import urllib.parse
    url = ("bear://x-callback-url/create?"
           + "title=" + urllib.parse.quote(title)
           + "&text="  + urllib.parse.quote(content)
           + "&tags="  + urllib.parse.quote("股票,日报"))
    subprocess.run(["open", url])
    print(f"📓 Bear: {title}")


# ── 主流程 ────────────────────────────────────────────
def main():
    now = datetime.now(CN_TZ)
    print(f"\n{'='*50}")
    print(f"📈 股票雷达 Pipeline 启动 {now.strftime('%Y-%m-%d %H:%M CST')}")
    print(f"{'='*50}\n")

    print("📡 Step 1/3：抓取数据...")
    run_fetch()

    print("\n📝 Step 2/3：生成报告...")
    with open(RAW_OUTPUT, encoding="utf-8") as f:
        data = json.load(f)

    # 宏观数据（pipeline层抓，不走subprocess）
    print("  🌍 宏观数据...")
    data["macro"]             = fetch_all_macro()
    data["rbnz"]              = fetch_rbnz_news()
    data["nzx_announcements"] = fetch_nzx_announcements()
    data["nzx_earnings"]      = fetch_nzx_earnings_calendar()

    print("  🤖 Groq 巴菲特分析...")
    ai_analysis = analyze_all(data)
    print(f"  ✅ 分析完成：{len(ai_analysis)} 只股票")

    report = generate_report(data, ai_analysis)
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 报告 {len(report)} 字符 → {REPORT_OUTPUT}")

    # ── 持久化到 SQLite ────────────────────────────────
    print("  💾 写入数据库...")
    _db.init_db()
    date_str = data["date"]

    # 行情
    for code, q in data.get("quotes", {}).items():
        _db.upsert_quote(code, date_str, q["price"], q["change"], q["amount"])

    # 新闻
    for code, items in data.get("news", {}).items():
        for n in items:
            _db.upsert_news(code, n["title"], n.get("source",""), n.get("link",""),
                            n.get("time",""), date_str)

    # 国际新闻
    for scope, items in data.get("intl_news", {}).items():
        for n in items:
            _db.upsert_intl_news(scope, n["title"], n.get("label",""),
                                 n.get("link",""), n.get("source",""), date_str)

    # 摩根大通新闻（作为市场洞察保存）
    for n in data.get("jpm_news", []):
        _db.upsert_intl_news("jpm_news", n["title"], "摩根大通",
                            n.get("link",""), n.get("source","摩根大通"), date_str)

    # 主力资金
    for code, ff in data.get("fund_flow", {}).items():
        if ff:
            _db.upsert_fund_flow(code, ff.get("date", date_str),
                                 ff.get("main_net", 0), ff.get("main_ratio", 0))

    # 报告（存 md；html 留空，后续可加 markdown→html 转换）
    _db.save_report(date_str, html="", md=report)
    print(f"  ✅ 数据库写入完成")

    print("\n📨 Step 3/3：推送...")

    # ── Admin：全量报告 → Bear + Discord + 全局 Server酱 ──
    save_to_bear(f"股票日报 {date_str}", report)
    send_discord_chunks(report)
    if SERVERCHAN_KEY:
        send_serverchan(SERVERCHAN_KEY, f"自选股日报 {date_str}", report)

    # ── Per-user：按 DB 持仓推送（notify_daily=1 的用户）──
    try:
        push_users = _db.get_users_with_daily_push()
    except Exception as e:
        push_users = []
        print(f"  ⚠️ 查询推送用户失败: {e}")

    for u in push_users:
        uid  = u["id"]
        name = u.get("display_name") or u["email"]
        key  = u.get("wecom_webhook", "")   # 存 SCT sendkey
        if not key:
            print(f"  ⚠️ {name} 无 wecom_webhook，跳过")
            continue

        print(f"  📲 生成 {name} 的个人日报...")
        content = build_user_push_content(uid, data, ai_analysis, date_str)
        if not content:
            print(f"    ⚠️ {name} 无持仓且无 A 级关注股，跳过")
            continue

        send_serverchan(key, f"股票日报 {date_str} — {name}", content)

    print(f"\n🎉 完成！{date_str} 股票日报已推送。")


if __name__ == "__main__":
    main()
