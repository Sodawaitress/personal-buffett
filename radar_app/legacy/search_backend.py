"""Thin adapters for legacy stock search module."""


def warm_search_backend():
    import stock_search as stock_search  # noqa: F401


def is_cn_search_loading():
    import stock_search
    return stock_search._CN_LOADING and stock_search._CN_CACHE is None


def search_stocks(query, limit=10):
    import stock_search
    return stock_search.search(query, limit=limit)
