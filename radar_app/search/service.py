"""Search service helpers."""

from flask import jsonify

from radar_app.legacy.search_backend import (
    is_cn_search_loading,
    is_fund_search_loading,
    search_stocks,
)

_LOADING_TYPES = {
    "cn":   is_cn_search_loading,
    "fund": is_fund_search_loading,
}


def search_payload(query, search_type="auto"):
    if len(query) < 1:
        return jsonify([])

    # Show loading spinner only for types whose cache is still warming up
    loader = _LOADING_TYPES.get(search_type)
    if loader is None and search_type == "auto":
        has_cn = any("\u4e00" <= c <= "\u9fff" for c in query) or query.isdigit()
        if has_cn:
            loader = is_cn_search_loading
    if loader and loader():
        return jsonify({"loading": True})

    return jsonify(search_stocks(query, limit=10, search_type=search_type))
