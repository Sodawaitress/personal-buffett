#!/usr/bin/env python3
"""
私人巴菲特 · 周期性摘要 (周/月/季)
用法：python periodic_digest.py weekly|monthly|quarterly
股票来自 DB 真实自选股，不使用硬编码。
"""

import sys, os, json, time, ssl, subprocess, urllib.request
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

from datetime import datetime, timedelta
import db as _db
from scripts.config import CN_TZ, DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID

PERIODS = {
    "weekly":    (7,  "本周",   "weekly"),
    "monthly":   (30, "本月",   "monthly"),
    "quarterly": (90, "本季度", "quarterly"),
}

NOISE_KEYWORDS   = ["技术分析","涨跌幅","换手率","主力资金日报","龙虎榜","融资融券"]
POSITIVE_SIGNALS = ["业绩","超预期","增持","回购","盈利","订单","合同","中标","扩产"]
NEGATIVE_SIGNALS = ["亏损","减持","处罚","立案","质押","爆仓","退市","违规","下滑","裁员"]


def _classify(title: str) -> str:
    if any(k in title for k in NOISE_KEYWORDS):   return "noise"
    if any(k in title for k in NEGATIVE_SIGNALS): return "negative"
    if any(k in title for k in POSITIVE_SIGNALS): return "positive"
    return "neutral"


def _call_groq(system: str, user_msg: str, max_tokens: int = 600) -> str:
    from scripts.config import GROQ_API_KEY
    import requests
    if not GROQ_API_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role":"system","content":system},
                                {"role":"user","content":user_msg}],
                  "max_tokens": max_tokens, "temperature": 0.3},
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠️ Groq: {e}")
        return ""


SYSTEM_PERIOD = """你是沃伦·巴菲特，为投资者撰写周期性持仓回顾。

写作风格：朴实、直接、有立场，像巴菲特年度股东信。
结构：先整体判断组合健康度，再逐一点评每只股票（一句话），最后给本期最值得关注的一只。
字数：250字以内。"""


def build_section(days: int, label: str) -> tuple:
    """
    返回 (markdown_table, ai_text)
    基于 DB 中所有用户自选股的真实数据。
    """
    _db.init_db()
    codes = _db.all_watched_codes()
    if not codes:
        return "（暂无自选股）", ""

    news_by_code   = {}
    quotes_by_code = {}
    fund_flows     = {}
    stock_infos    = {}

    for code in codes:
        stock = _db.get_stock(code)
        if not stock:
            continue
        stock_infos[code] = stock

        news = [n for n in _db.get_stock_news(code, days=days)
                if _classify(n.get("title","")) != "noise"]
        news_by_code[code] = news

        price = _db.get_latest_price(code)
        quotes_by_code[code] = price

        ff = _db.get_fund_flow(code)
        fund_flows[code] = ff or {}

    # 信号汇总表
    rows = []
    for code, stock in stock_infos.items():
        analysis = _db.get_latest_analysis(code, period="daily")
        grade    = analysis.get("grade", "—") if analysis else "—"
        news     = news_by_code.get(code, [])
        neg = sum(1 for n in news if _classify(n.get("title","")) == "negative")
        pos = sum(1 for n in news if _classify(n.get("title","")) == "positive")
        signal = "🔴" if neg >= 2 else ("🟢" if pos >= 1 else "🟡")
        q = quotes_by_code.get(code, {})
        pct = q.get("change_pct")
        pct_str = f"{pct:+.1f}%" if pct is not None else "—"
        name = stock.get("name", code)
        rows.append(f"| {name} | {grade} | {pct_str} | {signal} {pos}✅ {neg}⚠️ |")

    table = (
        "## 📊 信号汇总\n\n"
        "| 股票 | 评级 | 区间涨跌 | 信号 |\n"
        "|---|---|---|---|\n"
        + "\n".join(rows)
    ) if rows else "（本期无数据）"

    # AI 周期分析
    stocks_summary = []
    for code, stock in stock_infos.items():
        news = news_by_code.get(code, [])
        analysis = _db.get_latest_analysis(code, period="daily")
        grade = analysis.get("grade","?") if analysis else "?"
        ff = fund_flows.get(code, {})
        ff_str = f"资金净{'流入' if ff.get('main_net',0)>=0 else '流出'} {abs(ff.get('main_net',0)):.1f}亿" if ff.get("main_net") else ""
        pos_news = [n["title"][:60] for n in news if _classify(n.get("title",""))=="positive"]
        neg_news = [n["title"][:60] for n in news if _classify(n.get("title",""))=="negative"]
        parts = [f"**{stock['name']}**（评级{grade}）{ff_str}"]
        if pos_news: parts.append(f"  正面：{pos_news[0]}")
        if neg_news: parts.append(f"  负面：{neg_news[0]}")
        stocks_summary.append("\n".join(parts))

    if stocks_summary:
        user_msg = f"请为以下自选股撰写「{label}回顾」（过去{days}天）：\n\n" + "\n\n".join(stocks_summary)
        print(f"  🤖 Groq {label}分析...")
        ai_text = _call_groq(SYSTEM_PERIOD, user_msg)
    else:
        ai_text = ""

    return table, ai_text


def generate_report(mode: str) -> str:
    days, label, period = PERIODS[mode]
    now       = datetime.now(CN_TZ)
    date_str  = now.strftime("%Y-%m-%d")
    start_str = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    intros = {
        "weekly":    "每周日自动生成：过去7天的信号变化 + 巴菲特视角总结",
        "monthly":   "每月末自动生成：本月护城河变化 + 资本配置评估",
        "quarterly": "每季度末自动生成：组合健康检查 + 下季度关注重点",
    }

    header = f"# {label}回顾 {start_str} → {date_str}\n\n> {intros[mode]}\n"
    table, ai_text = build_section(days, label)
    buffett_section = f"\n## 🤖 巴菲特说\n\n{ai_text}" if ai_text else ""
    footer = (f"\n\n---\n*周期：{label} | 生成：{now.strftime('%Y-%m-%d %H:%M CST')}*\n"
              f"*评级：A=优质护城河 B=合格 C=周期/弱护城河 D=警报*")

    return header + "\n" + table + buffett_section + footer


def send_discord_chunks(content: str):
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        print("  ⚠️ Discord 未配置，跳过")
        return
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    url     = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}",
               "Content-Type": "application/json",
               "User-Agent": "DiscordBot (https://github.com, 1.0)"}
    chunks = []
    current = ""
    for line in content.split("\n## "):
        cand = current + ("\n## " if current else "") + line
        if len(cand) <= 1900:
            current = cand
        else:
            if current: chunks.append(current)
            current = "## " + line
    if current: chunks.append(current)

    sent = 0
    for chunk in chunks:
        payload = json.dumps({"content": chunk[:1990]}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                if r.status == 200: sent += 1
        except Exception as e:
            print(f"  ⚠️ Discord: {e}")
        time.sleep(0.5)
    print(f"📨 Discord：{sent}/{len(chunks)} 块")


def save_to_bear(title: str, content: str, period: str):
    import urllib.parse
    tags = {"weekly":"股票,周报","monthly":"股票,月报","quarterly":"股票,季报"}.get(period,"股票")
    url = ("bear://x-callback-url/create?"
           + "title=" + urllib.parse.quote(title)
           + "&text="  + urllib.parse.quote(content)
           + "&tags="  + urllib.parse.quote(tags))
    subprocess.run(["open", url])
    print(f"📓 Bear: {title}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    if mode not in PERIODS:
        print("用法：python periodic_digest.py weekly|monthly|quarterly")
        sys.exit(1)

    _, label, period = PERIODS[mode]
    now      = datetime.now(CN_TZ)
    date_str = now.strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"📅 {label}回顾 生成中... {date_str}")
    print(f"{'='*50}\n")

    report = generate_report(mode)

    _db.init_db()
    _db.save_report(date_str, html="", md=report, period=period)
    print(f"✅ 已存入数据库")

    title = f"私人巴菲特 {label}回顾 {date_str}"
    save_to_bear(title, report, period)
    send_discord_chunks(f"**{title}**\n\n" + report)
    print(f"\n🎉 {label}回顾完成！")


if __name__ == "__main__":
    main()
