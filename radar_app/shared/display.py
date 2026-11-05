"""US-224：分析结果里存的维度文字，显示前的最后一道清洗。

库里已有的分析是旧代码写的，缺分时存成了「None/30」「安全性 None/20」。
生成端已修（buffett_analyst 全走 _sc），这里兜住历史数据：缺分一律显示「—」，
不显示 None，也不显示 0（0 会被读成「得了 0 分」）。
"""

import re

_NONE_SCORE = re.compile(r"\bNone/\d+")
_PREFIX = {"安全性": "Safety"}


def dim_value(val, locale="zh"):
    if val is None:
        return "—"
    s = _NONE_SCORE.sub("—", str(val)).strip()
    if s in ("", "None"):
        return "—"
    if locale == "en":
        for zh, en in _PREFIX.items():
            if s.startswith(zh + " "):
                s = en + s[len(zh):]
    return s


def news_date(raw, locale="zh"):
    """新闻时间 → 日期（US-224）。原来模板直接 [:10] 截字符串，
    RSS 的 "Thu, 05 Nov 2026 10:00:00 +1300" 被截成「Thu, 05 No」。
    英文 "5 Nov"，中文 "11-05"；解析不了就原样返回（不截断）。"""
    if not raw:
        return ""
    from datetime import datetime
    from email.utils import parsedate_to_datetime
    s = str(raw).strip()
    dt = None
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        pass
    if dt is None:
        for fmt in ("%a, %d %b %Y",   # 抓取端已截成 "Thu, 05 Nov 2026"（无时分）
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s[:len(datetime(2000, 12, 30, 23, 59, 59).strftime(fmt))], fmt)
                break
            except Exception:
                continue
    if dt is None:
        return s
    return f"{dt.day} {dt:%b}" if locale == "en" else dt.strftime("%m-%d")
