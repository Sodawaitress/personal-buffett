"""Thin adapters for legacy stock search module."""

import time as _time

_LOAD_TIMEOUT = 40  # seconds: give up waiting after this long


def warm_search_backend():
    import stock_search  # noqa: F401

    # Flask debug mode forks a child process for the reloader. The parent's
    # background loading threads don't survive the fork, leaving the child with
    # _CN_LOADING=True but no thread to ever complete it. Detect that "orphan lock"
    # and kick off a fresh load in this process.
    for _cache_attr, _loading_attr, _ready_attr, _ts_attr in (
        ("_CN_CACHE",   "_CN_LOADING",   "_CN_READY",   "_CN_LOAD_TS"),
        ("_FUND_CACHE", "_FUND_LOADING", "_FUND_READY", "_FUND_LOAD_TS"),
        ("_ETF_CACHE",  "_ETF_LOADING",  "_ETF_READY",  None),
    ):
        loading = getattr(stock_search, _loading_attr, False)
        cache   = getattr(stock_search, _cache_attr,   None)
        if loading and cache is None:
            # Orphan lock: reset and let _prewarm() restart the load
            setattr(stock_search, _loading_attr, False)
            ready = getattr(stock_search, _ready_attr, None)
            if ready is not None:
                ready.clear()

    # Re-run prewarm if any cache is still missing
    if (stock_search._CN_CACHE is None and not stock_search._CN_LOADING) or \
       (stock_search._FUND_CACHE is None and not stock_search._FUND_LOADING):
        stock_search._prewarm()


def is_cn_search_loading():
    import stock_search
    if not stock_search._CN_LOADING or stock_search._CN_CACHE is not None:
        return False
    # Failsafe: if loading has taken > 40s, stop showing "loading" state
    if stock_search._CN_LOAD_TS and _time.time() - stock_search._CN_LOAD_TS > _LOAD_TIMEOUT:
        return False
    return True


def search_stocks(query, limit=10, search_type="auto"):
    import stock_search
    return stock_search.search_typed(query, search_type=search_type, limit=limit)


def is_fund_search_loading():
    import stock_search
    if not stock_search._FUND_LOADING or stock_search._FUND_CACHE is not None:
        return False
    if stock_search._FUND_LOAD_TS and _time.time() - stock_search._FUND_LOAD_TS > _LOAD_TIMEOUT:
        return False
    return True
