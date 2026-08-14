"""北向资金数据源的存活判定（US-151）。

单独成模块而不是放进 institutional_radar：那个模块会拉进 akshare，
单这一个 import 就要 ~43 秒。数据层 radar_app/data/market.py 只是想
算个日期差，不该为此加载整个 akshare。本模块只依赖 datetime。
"""

from datetime import date as _date

# 净流入绝对值小于这个数（亿元）视为「零」，既不算流入也不算流出。
NB_EPSILON = 0.01

# 超过这么多自然日没有新数据，就认定数据源已停更。
# 北向是交易日数据，7 天足以跨过任何一个长假的前半段而不误杀。
NB_STALE_DAYS = 7


def _parse(s: str):
    try:
        y, m, d = (int(x) for x in str(s).split("-")[:3])
        return _date(y, m, d)
    except (ValueError, TypeError, AttributeError):
        return None


def is_northbound_stale(as_of: str, today: str = "") -> bool:
    """北向数据是否已停更。as_of / today 都是 'YYYY-MM-DD'。

    2026-07 官方停止公布日度北向数据后，akshare 持续返回 0.0 / 空，而
    `northbound_history` 里 07-09 那条旧记录会被下游当成「今天的值」。
    没有这个判定，一串 0.0 会被读成「外资连续 N 天买入」——凭空的看多证据。
    """
    latest = _parse(as_of)
    if latest is None:
        return True
    ref = _parse(today) if today else _date.today()
    if ref is None:
        ref = _date.today()
    return (ref - latest).days > NB_STALE_DAYS
