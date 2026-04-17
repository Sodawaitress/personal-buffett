"""
股票雷达 · 组合日报简报生成
每日 16:05 CST 由 launchd 调用，或用户点「生成简报」手动触发。
LLM 读取所有持仓的最新分析 + 宏观数据，生成一份个性化的巴菲特视角总结。
"""

import sys, os, json, requests
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

from scripts.config import GROQ_API_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.3-70b-versatile"

SYSTEM_BRIEF = """你是一位按巴菲特视角行事的私人投资顾问，为一位中国普通投资者服务。

今天你要写一份简短的「组合日报」，包含两部分：
1. 宏观一句话：根据提供的市场数据，用一句话说明今天的市场环境和对持仓的含义（不超过30字）
2. 巴菲特总结：针对用户整体持仓，给出3句具体建议（每句15-25字），风格直接、有立场

注意：
- 宏观分析要联系到持仓的实际影响，不要泛泛而谈
- 如果有明显风险，直接说出来
- 如果总体安全，也要给出"接下来最值得关注的一件事"
- 用中文，语气朴实直接，像写给朋友的备忘录

严格按以下格式输出，不要多余文字：
宏观：[一句话]
建议：[第一句]。[第二句]。[第三句]。"""


def _call_groq(system: str, user_msg: str, max_tokens: int = 400) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens":  max_tokens,
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠️ portfolio_brief Groq: {e}")
        return ""


def _parse_response(text: str) -> tuple[str, str]:
    """从 LLM 输出提取 (macro_headline, buffett_summary)。"""
    macro, summary = "", ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("宏观："):
            macro = line[3:].strip()
        elif line.startswith("建议："):
            summary = line[3:].strip()
    # 容错：如果格式不对，把整段作为 summary
    if not macro and not summary:
        summary = text[:300]
    return macro, summary


def generate_portfolio_brief(stocks_data: list, market_data: dict, locale: str = "zh") -> tuple[str, str]:
    """
    生成组合日报简报。

    Args:
        stocks_data: list of dicts, 每只股票的分析摘要
            {code, name, market, grade, conclusion, reasoning, moat, behavioral, main_net}
        market_data: dict, 宏观数据快照 (fear_greed, cn_indices, cny_usd, etc.)
        locale: "zh" 中文 | "en" 英文（老师 demo 用）

    Returns:
        (macro_headline, buffett_summary)
    """
    if not stocks_data:
        return "", ""

    # 构建持仓摘要
    holdings_lines = []
    for s in stocks_data:
        grade     = s.get("grade") or "—"
        name      = s.get("name") or s.get("code")
        conc      = s.get("conclusion") or ""
        reasoning = (s.get("reasoning") or "")[:60]
        net       = s.get("main_net")
        net_str   = f"主力净{'+' if net >= 0 else ''}{net:.2f}亿" if net is not None else ""
        holdings_lines.append(f"- {name}（{grade} {conc}）{net_str}：{reasoning}")

    holdings_text = "\n".join(holdings_lines)

    # 构建宏观摘要
    macro_lines = []
    fg = market_data.get("fear_greed", {})
    if fg and fg.get("score") is not None:
        macro_lines.append(f"CNN Fear&Greed: {fg['score']} {fg.get('label','')}")
    idx = market_data.get("cn_indices", {})
    if idx:
        for key, name in [("sh","上证"),("sz","深证"),("cyb","创业板")]:
            i = idx.get(key)
            if i:
                macro_lines.append(f"{name} {i.get('price','')} ({'+' if i.get('change',0)>=0 else ''}{i.get('change',0):.2f}%)")
    cny = market_data.get("cny_usd", {})
    if cny and cny.get("rate"):
        macro_lines.append(f"USD/CNY {cny['rate']} {cny.get('direction','')}")

    macro_text = "、".join(macro_lines) if macro_lines else "暂无宏观数据"

    user_msg = f"""今日宏观数据：
{macro_text}

用户当前持仓（{len(stocks_data)}只）：
{holdings_text}"""

    if locale == "en":
        system = SYSTEM_BRIEF.replace("中国普通投资者", "retail investor in New Zealand").replace(
            "中文", "English").replace("宏观：", "Macro:").replace("建议：", "Advice:")

    raw = _call_groq(SYSTEM_BRIEF if locale == "zh" else system, user_msg, max_tokens=400)
    return _parse_response(raw)


if __name__ == "__main__":
    # 快速测试
    import db

    db.init_db()
    users = []
    with db.get_conn() as c:
        users = [dict(r) for r in c.execute("SELECT id FROM users").fetchall()]

    for u in users:
        wl = db.get_user_watchlist(u["id"])
        stocks_data = []
        for row in wl:
            code = row.get("stock_code") or row.get("code")
            a = db.get_latest_analysis(code, period="daily")
            ff = db.get_fund_flow(code)
            if a:
                stocks_data.append({
                    "code":      code,
                    "name":      row.get("name", code),
                    "grade":     a.get("grade"),
                    "conclusion":a.get("conclusion"),
                    "reasoning": a.get("reasoning"),
                    "moat":      a.get("moat"),
                    "behavioral":a.get("behavioral"),
                    "main_net":  ff.get("main_net") if ff else None,
                })
        snap = db.get_market_snapshot()
        market_data = snap.get("data", {}) if snap else {}
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        macro, summary = generate_portfolio_brief(stocks_data, market_data)
        print(f"User {u['id']}:")
        print(f"  宏观：{macro}")
        print(f"  建议：{summary}")
        if macro or summary:
            db.save_portfolio_brief(u["id"], today, macro, summary)
            print("  ✓ saved")
