"""Standardized JSON response helpers for API endpoints.

All new /api/* endpoints should use ok() / err() so Next.js can rely on
a consistent envelope: { "ok": true, "data": {...} } or
{ "ok": false, "error": "...", "code": "SNAKE_CASE" }.

Existing endpoints consumed by template JS retain their original shape
until those templates are replaced by Next.js pages.
"""

from flask import jsonify


def ok(data=None, **kwargs):
    """Return 200 JSON envelope: { ok: true, data: <payload> }."""
    payload = {"ok": True, "data": data if data is not None else {}}
    if kwargs:
        payload.update(kwargs)
    return jsonify(payload), 200


def err(message: str, code: str = "ERROR", status: int = 400):
    """Return error JSON envelope: { ok: false, error: <msg>, code: <CODE> }."""
    return jsonify({"ok": False, "error": message, "code": code}), status
