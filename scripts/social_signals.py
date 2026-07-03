"""
US-112 · 未定价信号：社交套利数据层
三层数据：A 自动信号 / B 用户打分 / C 独家洞察
"""
import json
import re
import time
import requests
from datetime import datetime, timedelta

from scripts.buffett_groq import _call_groq


# ── A 层：Google Trends ──────────────────────────────────────────────────

def fetch_google_trends(query: str, days: int = 90) -> dict:
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25),
                      requests_args={"headers": {"User-Agent": "Mozilla/5.0"}})
        pt.build_payload([query], timeframe=f"today {days}-d")
        df = pt.interest_over_time()
        if df.empty or query not in df.columns:
            return {"slope": 0, "sparkline": [], "ok": False, "reason": "no_data"}
        vals = df[query].tolist()
        n = len(vals)
        if n < 6:
            return {"slope": 0, "sparkline": vals, "ok": False, "reason": "too_few"}
        third = max(n // 3, 1)
        first_avg = sum(vals[:third]) / third or 1
        last_avg  = sum(vals[-third:]) / third
        slope = round((last_avg - first_avg) / first_avg, 3)
        return {"slope": slope, "sparkline": vals[-30:], "ok": True}
    except Exception as e:
        print(f"    [trends] {e}")
        return {"slope": 0, "sparkline": [], "ok": False, "reason": str(e)[:60]}


def _trends_score(d: dict) -> int:
    if not d.get("ok"):
        return 10  # 数据不可用时给中性分
    s = d["slope"]
    if s >= 1.0:  return 24
    if s >= 0.5:  return 20
    if s >= 0.2:  return 16
    if s >= 0.0:  return 12
    if s >= -0.2: return 7
    return 3


# ── A 层：Reddit 提及量 ────────────────────────────────────────────────────

def fetch_reddit_mentions(query: str) -> dict:
    hdrs = {"User-Agent": "PersonalBuffett/1.0 (research tool)"}
    try:
        r_month = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "new", "t": "month", "limit": 100},
            headers=hdrs, timeout=12
        )
        r_year = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "new", "t": "year", "limit": 100},
            headers=hdrs, timeout=12
        )
        recent = len(r_month.json()["data"]["children"]) if r_month.ok else 0
        annual = len(r_year.json()["data"]["children"])  if r_year.ok  else 0
        monthly_avg = max(annual / 12, 1)
        trend_pct = round((recent - monthly_avg) / monthly_avg * 100, 1)
        return {"recent_30": recent, "monthly_avg": round(monthly_avg, 1),
                "trend_pct": trend_pct, "ok": True}
    except Exception as e:
        print(f"    [reddit] {e}")
        return {"recent_30": 0, "monthly_avg": 0, "trend_pct": 0, "ok": False}


def _reddit_score(d: dict) -> int:
    if not d.get("ok"):
        return 9
    p = d["trend_pct"]
    if p >= 150: return 20
    if p >= 80:  return 17
    if p >= 30:  return 14
    if p >= 0:   return 11
    if p >= -20: return 7
    return 3


# ── A 层：新闻频率（越少越早，反向分）──────────────────────────────────────

def fetch_news_frequency(code: str) -> dict:
    from radar_app.data.core import get_engine
    from sqlalchemy import text
    try:
        from datetime import datetime as _dt, timedelta as _td
        _cut = (_dt.utcnow() - _td(days=7)).strftime("%Y-%m-%d")
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COUNT(*) FROM stock_news "
                "WHERE code=:code AND publish_time >= :cut"
            ), {"code": code, "cut": _cut}).fetchone()
            count_7d = row[0] if row else 0
        return {"count_7d": count_7d, "ok": True}
    except Exception as e:
        print(f"    [news_freq] {e}")
        return {"count_7d": 0, "ok": False}


def _news_freq_score(d: dict) -> int:
    if not d.get("ok"):
        return 9
    n = d["count_7d"]
    # 反向：新闻越少 = 市场越没注意到 = 分越高
    if n == 0:  return 16
    if n <= 2:  return 13
    if n <= 5:  return 10
    if n <= 10: return 6
    return 2


# ── A 层：分析师覆盖度（反向，越少越早）──────────────────────────────────────

def fetch_analyst_coverage(code: str) -> dict:
    from radar_app.data.core import get_engine
    from sqlalchemy import text
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT data_json FROM analyst_consensus WHERE code=:code"
            ), {"code": code}).fetchone()
        if not row or not row[0]:
            return {"count": 0, "ok": True}
        data = json.loads(row[0])
        count = data.get("institution_count") or len(data.get("forecasts", []))
        return {"count": int(count), "ok": True}
    except Exception as e:
        print(f"    [analyst_cov] {e}")
        return {"count": 0, "ok": False}


def _analyst_score(d: dict) -> int:
    if not d.get("ok"):
        return 8
    n = d["count"]
    if n == 0:   return 15  # 无机构覆盖 = 信息尚未定价
    if n <= 5:   return 10
    if n <= 15:  return 5
    return 0  # 大量机构覆盖 = 信息充分定价


# ── A 层合计（满分 75）────────────────────────────────────────────────────

def compute_auto_score(code: str, query: str) -> dict:
    trends  = fetch_google_trends(query)
    time.sleep(1)
    reddit  = fetch_reddit_mentions(query)
    news    = fetch_news_frequency(code)
    analyst = fetch_analyst_coverage(code)

    t = _trends_score(trends)
    r = _reddit_score(reddit)
    n = _news_freq_score(news)
    a = _analyst_score(analyst)
    raw_total = t + r + n + a  # max 75
    # 归一化到 60（保持 B+C 层总分 100 不变）
    total = round(raw_total * 60 / 75)

    return {
        "total": total,
        "breakdown": {"trends": t, "reddit": r, "news": n, "analyst": a},
        "raw": {
            "trends":  trends,
            "reddit":  reddit,
            "news":    news,
            "analyst": analyst,
        },
    }


# ── B 层：用户结构化打分（满分 40）──────────────────────────────────────────

_DISCOVERY = {"daily_life": 15, "friend": 10, "social_media": 8,
              "finance_news": 3, "analyst": 0}
_AWARENESS = {"nobody": 15, "small_circle": 10, "friends_know": 5, "everyone": 0}
_PHYSICAL  = {"empty_shelf": 5, "queue": 5, "ad_appeared": 3, "low_price": 3}

def compute_user_score(discovery: str, awareness: str, physical: list) -> int:
    d = _DISCOVERY.get(discovery, 0)
    a = _AWARENESS.get(awareness, 0)
    p = sum(_PHYSICAL.get(s, 0) for s in (physical or []))
    return min(d + a + p, 40)


# ── C 层：Groq 判断独家洞察（-15 ~ +15）─────────────────────────────────────

_SYSTEM_INSIGHT = """你是一个评估「社交套利投资信号」质量的专家。

Chris Camillo 方法核心：找到市场还没消化的信息，在被定价前进场。
强信号特征：亲身目击 + 具体细节 + 逻辑自洽 + 市场确实还不知道。
矛盾信号：观察本身包含削弱因素或自相矛盾。
反向信号：暗示趋势已饱和或下行。

只输出 JSON，不加任何其他文字：
{"signal_type":"strong|neutral|contradiction|reverse","adjustment":<整数-15到15>,"reasoning":"<中文,40字以内>"}"""

def judge_insight(insight_text: str, stock_name: str) -> dict:
    if not (insight_text or "").strip():
        return {"signal_type": "none", "adjustment": 0, "reasoning": ""}
    raw = _call_groq(
        _SYSTEM_INSIGHT,
        f"股票：{stock_name}\n用户观察：{insight_text.strip()}",
        max_tokens=120,
    )
    try:
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {"signal_type": "neutral", "adjustment": 0, "reasoning": "解析失败"}


# ── 综合分数 + 标签 ────────────────────────────────────────────────────────

def digest_label(score: int) -> str:
    if score >= 85: return "极早期"
    if score >= 65: return "早期"
    if score >= 45: return "扩散中"
    if score >= 25: return "进主流"
    return "已公开"

def digest_emoji(score: int) -> str:
    if score >= 65: return "🟢"
    if score >= 45: return "🟡"
    return "🔴"

def compute_total(auto: int, user_b: int, insight_adj: int) -> int:
    return max(0, min(100, auto + user_b + insight_adj))
