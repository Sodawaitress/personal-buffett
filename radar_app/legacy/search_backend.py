"""Thin adapters for legacy stock search module."""


def warm_search_backend():
    import stock_search as stock_search  # noqa: F401


def is_cn_search_loading():
    import stock_search
    # Only block on A-share stock list; ETF/fund load non-blocking in background
    return stock_search._CN_LOADING and stock_search._CN_CACHE is None


def search_stocks(query, limit=10, search_type="auto"):
    import stock_search
    return stock_search.search_typed(query, search_type=search_type, limit=limit)


def is_fund_search_loading():
    import stock_search
    return stock_search._FUND_LOADING and stock_search._FUND_CACHE is None
