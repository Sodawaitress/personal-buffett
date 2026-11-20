"""Thin adapters for legacy market/news modules.

这些函数会在页面请求里被同步调用，所以都套了 bounded()：缓存 + 单飞 + 最多等几秒。
见 radar_app/shared/bounded_fetch.py 的事故说明。脚本/流水线直接 import 原模块，不受影响。
"""

import macro_fetch as _macro
import nz_fetch as _nz
from nz_profiles import NZ_PROFILES, NZ_SECTORS
from radar_app.shared.bounded_fetch import bounded

_NEWS_TTL = 15 * 60
_WAIT = 4

fetch_cn_market_news = bounded(_NEWS_TTL, _WAIT, list)(_macro.fetch_cn_market_news)
fetch_fomc_news = bounded(30 * 60, _WAIT, list)(_macro.fetch_fomc_news)
fetch_nz_market_news = bounded(_NEWS_TTL, _WAIT, list)(_nz.fetch_nz_market_news)
fetch_rbnz_news = bounded(_NEWS_TTL, _WAIT, list)(_nz.fetch_rbnz_news)
fetch_nzx50 = bounded(5 * 60, _WAIT, dict)(_nz.fetch_nzx50)
fetch_all_nz_quotes = _nz.fetch_all_nz_quotes  # 只在后台任务里用，慢是正常的

__all__ = [
    "NZ_PROFILES",
    "NZ_SECTORS",
    "fetch_all_nz_quotes",
    "fetch_cn_market_news",
    "fetch_fomc_news",
    "fetch_nz_market_news",
    "fetch_nzx50",
    "fetch_rbnz_news",
]
