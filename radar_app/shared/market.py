"""Shared market helpers."""

import re

MARKET_CURRENCY = {"cn": "¥", "nz": "NZ$", "hk": "HK$", "us": "$", "kr": "₩", "au": "A$"}


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
