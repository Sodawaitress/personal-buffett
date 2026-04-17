"""Thin adapters for legacy market/news modules."""

from macro_fetch import fetch_fomc_news
from nz_fetch import fetch_all_nz_quotes, fetch_nz_market_news, fetch_nzx50, fetch_rbnz_news
from nz_profiles import NZ_PROFILES, NZ_SECTORS

__all__ = [
    "NZ_PROFILES",
    "NZ_SECTORS",
    "fetch_all_nz_quotes",
    "fetch_fomc_news",
    "fetch_nz_market_news",
    "fetch_nzx50",
    "fetch_rbnz_news",
]
