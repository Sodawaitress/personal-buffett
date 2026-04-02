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


# ── 运行抓取 ──────────────────────────────────────────
def run_fetch():
    script = os.path.join(os.path.dirname(__file__), "stock_fetch.py")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"⚠️ {result.stderr[:300]}")


# ── 生成报告 ──────────────────────────────────────────
def generate_report(data: dict, ai_analysis: dict = None) -> str:
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

    stock_sections = []
    for name, code, desc in WATCHLIST:
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
    for name, code, _ in WATCHLIST:
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
    for name, code, _ in WATCHLIST:
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

    report = f"""# 📈 自选股日报 {date}

{buffett_summary}

## 📊 今日行情

| 股票 | 现价 | 涨跌幅 | 成交额 |
|---|---|---|---|
""" + "\n".join(quote_lines) + f"""

{nb_line}
{lhb_section}
## 📰 个股动态（巴菲特视角）

""" + "\n\n".join(stock_sections) + """

## 🌐 国际视角

""" + "\n".join(intl_lines) + """

## 🗞️ 板块·政策快讯

""" + "\n".join(sector_lines) + f"""

---
*数据来源：新浪财经·东方财富·财联社 · {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M CST')}*
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

    # 主力资金
    for code, ff in data.get("fund_flow", {}).items():
        if ff:
            _db.upsert_fund_flow(code, ff.get("date", date_str),
                                 ff.get("main_net", 0), ff.get("main_ratio", 0))

    # 报告（存 md；html 留空，后续可加 markdown→html 转换）
    _db.save_report(date_str, html="", md=report)
    print(f"  ✅ 数据库写入完成")

    print("\n📨 Step 3/3：推送...")
    save_to_bear(f"股票日报 {date_str}", report)
    send_discord_chunks(report)

    send_wechat(f"自选股日报 {date_str}", report)

    print(f"\n🎉 完成！{date_str} 股票日报已推送。")


if __name__ == "__main__":
    main()
