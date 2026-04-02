"""
股票雷达 · 巴菲特 AI 分析模块
使用 Groq (Llama 3) 免费 API，对每只有实质性新闻的股票生成巴菲特视角点评
"""

import json, time, requests
from config import BUFFETT_PROFILES, GROQ_API_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.3-70b-versatile"   # 免费，理解中文好

# ── 巴菲特 System Prompt ──────────────────────────────
SYSTEM = """你是一位严格遵循巴菲特价值投资框架的分析师助手，服务于一位中国A股散户投资者的妈妈。

你的分析框架：
1. 护城河完好性：今日新闻是否动摇了这家公司的竞争优势？
2. 管理层信号：有无「机构惯性」警报（CEO/CFO离职、盲目扩张、减持）？
3. 主力资金：机构今日是在积累还是出逃？
4. 持有人建议：基于巴菲特「持有 / 观望 / 警惕」三档给出明确建议

输出要求：
- 用简洁口语化的中文，像对着妈妈讲话一样易懂
- 总长度控制在 3-5 句话
- 必须给出明确结论：「继续持有」「暂时观望」或「需要警惕」
- 不要废话，不要免责声明
"""


def analyze_stock(name: str, code: str, news: list, fund_flow: dict, quote: dict) -> str:
    """
    对单只股票生成巴菲特视角分析。
    返回 2-4 句中文分析字符串，出错返回空字符串。
    """
    profile = BUFFETT_PROFILES.get(code, {})
    if not profile:
        return ""

    # 只分析有新闻的股票，节省 API 调用
    if not news:
        return ""

    # 构建新闻摘要
    news_lines = "\n".join(
        f"- {n['title']}（{n.get('source','')}）"
        for n in news[:5]
    )

    # 主力资金方向
    ff_str = ""
    if fund_flow:
        net   = fund_flow.get("main_net", 0)
        ratio = fund_flow.get("main_ratio", 0)
        ff_str = f"主力资金净{'流入' if net >= 0 else '流出'} {abs(net):.2f}亿（占比{ratio:.1f}%）"

    # 今日涨跌
    price_str = ""
    if quote:
        price_str = f"今日 ¥{quote.get('price', 0):.2f}（{quote.get('change', 0):+.2f}%）"

    user_msg = f"""请分析以下股票：

股票：{name}（{code}）
巴菲特评级：{profile.get('grade', '?')}级
护城河：{profile.get('moat', '')}
近5年ROE：{profile.get('roe_5y', '')}
核心风险：{profile.get('key_risk', '')}
重点关注：{', '.join(profile.get('watch', []))}
{price_str}
{ff_str}

今日新闻：
{news_lines}

请给出巴菲特视角的简短分析和明确建议。"""

    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":    MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens":   300,
                "temperature":  0.3,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    ⚠️ Groq 分析 {name}: {e}")
        return ""


def analyze_all(data: dict) -> dict:
    """
    分析所有自选股，返回 {code: analysis_text} 字典。
    自动限速：Groq 免费版 30 RPM，每次请求后等 2 秒。
    """
    from config import WATCHLIST
    results = {}
    news_map      = data.get("news", {})
    fund_flow_map = data.get("fund_flow", {})
    quotes_map    = data.get("quotes", {})

    for name, code, _ in WATCHLIST:
        stock_news = news_map.get(code, [])
        if not stock_news:
            continue  # 无新闻不调用 API

        print(f"    🤖 Groq 分析 {name}...")
        text = analyze_stock(
            name      = name,
            code      = code,
            news      = stock_news,
            fund_flow = fund_flow_map.get(code, {}),
            quote     = quotes_map.get(code, {}),
        )
        if text:
            results[code] = text
        time.sleep(2)   # 限速

    return results
