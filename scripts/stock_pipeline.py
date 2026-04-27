#!/usr/bin/env python3
"""
股票雷达 · 全流程 Pipeline
每日 8:30 自动运行：抓取 → 生成报告 → 推送 Discord
"""

import sys, os
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import json, subprocess, ssl, time, urllib.request
from datetime import datetime
import db as _db
from scripts.config import (
    RAW_OUTPUT, REPORT_OUTPUT,
    DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, CN_TZ,
    SERVERCHAN_KEY
)
from scripts.stock_report import build_user_push_content, generate_report
from scripts.buffett_analyst import analyze_all
from scripts.macro_fetch import fetch_all_macro
from scripts.nz_fetch import fetch_rbnz_news, fetch_nzx_announcements, fetch_nzx_earnings_calendar
from scripts.stock_fetch import fetch_cn_earnings_calendar
from scripts.institutional_radar import run_institutional_radar


# ── 运行抓取 ──────────────────────────────────────────
def run_fetch():
    script = os.path.join(os.path.dirname(__file__), "stock_fetch.py")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"⚠️ {result.stderr[:300]}")


# ── 生成报告 ──────────────────────────────────────────
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


def _refresh_user_holdings_layer2(date_str: str):
    """
    收盘后对所有用户的持仓股跑一次 Layer 2（纯数学，零 LLM）。
    刷新量化评级 + trading_params 存入 DB，让今日推送用上今天的数据。
    """
    from scripts.pipeline import _run_layer2
    import threading

    # 收集所有需要刷新的代码（去重）
    push_users = _db.get_users_with_daily_push()
    codes_to_refresh = set()
    for u in push_users:
        holdings = _db.get_user_holdings(u["id"])
        watching = _db.get_user_watching(u["id"])
        codes_to_refresh.update(holdings)
        codes_to_refresh.update(watching)

    if not codes_to_refresh:
        return

    print(f"  📊 Layer 2 刷新 {len(codes_to_refresh)} 只股票的量化评级...")
    refreshed = 0
    for code in sorted(codes_to_refresh):
        stock = _db.get_stock(code)
        market = (stock or {}).get("market", "cn")
        logs = []
        try:
            _run_layer2(code, market, lambda msg: logs.append(msg))
            refreshed += 1
        except Exception as e:
            print(f"    ⚠️ {code} Layer 2 失败: {e}")

    print(f"  ✅ Layer 2 刷新完成：{refreshed}/{len(codes_to_refresh)} 只")


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


# ── 交易日判断 ────────────────────────────────────────
def _is_trading_day(dt) -> bool:
    """
    简单判断是否 A 股交易日：排除周六/周日。
    节假日未做精确判断（AKShare 无稳定离线日历），收盘后行情全为 0 会被后续逻辑忽略。
    """
    return dt.weekday() < 5   # 0=Monday … 4=Friday


# ── 主流程 ────────────────────────────────────────────
def main():
    now = datetime.now(CN_TZ)
    print(f"\n{'='*50}")
    print(f"📈 股票雷达 Pipeline 启动 {now.strftime('%Y-%m-%d %H:%M CST')}")
    print(f"{'='*50}\n")

    trading_day = _is_trading_day(now)
    if not trading_day:
        print(f"📅 今日为休息日（{now.strftime('%A')}），仅收集新闻，跳过行情 & AI 分析\n")

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

    date_str = data["date"]

    if not trading_day:
        # 休息日：只存新闻，不跑 AI 分析，不生成报告，不推送
        print("  ⏭️ 休息日：跳过 AI 分析和报告生成")
        _db.init_db()
        for code, items in data.get("news", {}).items():
            for n in items:
                _db.upsert_news(code, n["title"], n.get("source",""), n.get("link",""),
                                n.get("time",""), date_str)
        for scope, items in data.get("intl_news", {}).items():
            for n in items:
                _db.upsert_intl_news(scope, n["title"], n.get("label",""),
                                     n.get("link",""), n.get("source",""), date_str)
        print(f"✅ 休息日新闻已入库，pipeline 结束")
        return

    print("  🤖 Groq 巴菲特分析...")
    ai_analysis = analyze_all(data)
    print(f"  ✅ 分析完成：{len(ai_analysis)} 只股票")

    # ── 收盘后刷新所有用户持仓的量化评级（Layer 2，零 LLM token）──
    _refresh_user_holdings_layer2(date_str)

    print("\n🏦 Step 2.5/3：机构雷达...")
    institutional_section = run_institutional_radar(data)

    report = generate_report(data, ai_analysis)
    report = report + "\n\n" + institutional_section
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 报告 {len(report)} 字符 → {REPORT_OUTPUT}")

    # ── 持久化到 SQLite ────────────────────────────────
    print("  💾 写入数据库...")
    _db.init_db()

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
