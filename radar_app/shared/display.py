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
