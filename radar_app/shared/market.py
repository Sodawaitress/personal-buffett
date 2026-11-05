"""Shared market helpers."""

import re

# US-224：美股写 US$ —— 新西兰读者看到光秃秃的 $ 会当成新西兰元
MARKET_CURRENCY = {"cn": "¥", "nz": "NZ$", "hk": "HK$", "us": "US$", "kr": "₩", "au": "A$"}


def compact_amount(value, locale="zh", currency="", signed=False, zh_decimals=0):
    """大额数字的显示（US-224）。中文按「亿」（和以前一模一样），英文按 K/M/B/T 加货币符号。

    中文：compact_amount(4.1e9) → "41亿"；signed + zh_decimals=2 → "+41.00亿"
    英文：compact_amount(4.1e9, "en", "NZ$") → "NZ$4.1B"；signed → "+NZ$4.1B"
    """
    if value is None:
        return "—"
    v = float(value)
    if locale == "zh":
        fmt = "%+.{}f亿" if signed else "%.{}f亿"
        return (fmt.format(zh_decimals)) % (v / 1e8)
    sign = ("+" if v >= 0 else "−") if signed else ("−" if v < 0 else "")
    a = abs(v)
    for div, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            n = a / div
            num = f"{n:.0f}" if n >= 100 else f"{n:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{currency}{num}{unit}"
    return f"{sign}{currency}{a:.0f}"


def detect_market(code):
    if code.endswith(".NZ"):
        return "nz"
    if code.endswith(".HK"):
        return "hk"
    if code.endswith(".KS") or code.endswith(".KQ"):
        return "kr"
    if code.endswith(".AX"):
        return "au"
    if re.match(r"^\d{5}$", code):
        return "hk"
    if re.match(r"^\d{6}$", code):
        return "cn"
    return "us"
