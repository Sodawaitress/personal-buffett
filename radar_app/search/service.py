"""Search service helpers."""

from flask import jsonify

from radar_app.legacy.search_backend import is_cn_search_loading, search_stocks


def search_payload(query):
    if len(query) < 1:
        return jsonify([])

    has_cn = any("\u4e00" <= char <= "\u9fff" for char in query) or query.isdigit()
    if has_cn and is_cn_search_loading():
        return jsonify({"loading": True})
    return jsonify(search_stocks(query, limit=10))
