"""Knowledge card API endpoint."""

from flask import jsonify, request

from radar_app.knowledge.service import match_situation

_FLOAT_FIELDS = {"change_pct", "price_change_pct", "latest", "avg_30d", "score"}
_INT_FIELDS   = {"n_inst", "days_ago", "event_count"}
_BOOL_FIELDS  = {"spike", "has_specific", "short_increasing", "pa_spike"}


def _coerce(raw: dict) -> dict:
    data = {}
    for k, v in raw.items():
        if k in _FLOAT_FIELDS:
            try: data[k] = float(v)
            except (TypeError, ValueError): pass
        elif k in _INT_FIELDS:
            try: data[k] = int(v)
            except (TypeError, ValueError): pass
        elif k in _BOOL_FIELDS:
            data[k] = str(v).lower() in ("true", "1", "yes")
        else:
            data[k] = v
    return data


def register_knowledge_routes(app):
    @app.route("/api/knowledge/<slug>")
    def knowledge_card(slug):
        data = _coerce(dict(request.args))
        result = match_situation(slug, data)
        if not result:
            return jsonify({"error": "no match"}), 404
        return jsonify(result)
