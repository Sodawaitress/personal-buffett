"""Knowledge card service: loads YAML situation files and matches signal data."""

import os
import yaml

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "../../knowledge")

_cache: dict = {}


def _load(slug: str) -> dict:
    if slug not in _cache:
        path = os.path.join(_KNOWLEDGE_DIR, f"{slug}.yaml")
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            _cache[slug] = yaml.safe_load(f) or {}
    return _cache[slug]


def _matches(triggers, data: dict) -> bool:
    if triggers is None:
        return True
    for cond in triggers.get("all", []):
        field = cond["field"]
        op    = cond["op"]
        value = cond["value"]
        actual = data.get(field)
        if actual is None:
            return False
        if   op == ">":  ok = actual >  value
        elif op == "<":  ok = actual <  value
        elif op == ">=": ok = actual >= value
        elif op == "<=": ok = actual <= value
        elif op == "==": ok = actual == value
        elif op == "!=": ok = actual != value
        else:            ok = False
        if not ok:
            return False
    return True


def match_situation(slug: str, data: dict) -> dict | None:
    """Return the first matching situation card for the given signal data."""
    spec = _load(slug)
    if not spec:
        return None
    for sit in spec.get("situations", []):
        if _matches(sit.get("triggers"), data):
            return {
                "name":      spec.get("name", slug),
                "one_liner": spec.get("one_liner", ""),
                "situation": sit.get("label", ""),
                "body":      (sit.get("body") or "").strip(),
                "note":      (sit.get("note") or "").strip(),
            }
    return None


def list_slugs() -> list[str]:
    try:
        return [f[:-5] for f in os.listdir(_KNOWLEDGE_DIR) if f.endswith(".yaml")]
    except Exception:
        return []
