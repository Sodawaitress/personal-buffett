"""Shared i18n helpers.

Source of truth: i18n/<module>.json files (one per feature domain).
Each file has the structure: { "key": { "en": "...", "zh": "..." } }

Adding a new string:
  1. Open the relevant module file (e.g. i18n/watchlist.json)
  2. Add the key with both "en" and "zh" values in the same entry
  3. Use {{ t.your_key }} in the template — done

Missing locale value falls back to "en".
Completely missing key renders as [key] so it shows up immediately in the UI.
"""

import json
import logging
import os
from typing import ClassVar

_I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "i18n")

# Module files — add new ones here when you create a new feature module
MODULES = ("common", "auth", "home", "watchlist", "stock", "admin", "settings")

_raw: dict | None = None          # merged {key: {locale: value}}
_cache: dict[str, dict] = {}      # locale → {key: translated_string}


def _load_all() -> dict:
    """Load and merge all module files. Called once; result is cached."""
    global _raw
    if _raw is not None:
        return _raw
    merged: dict = {}
    for module in MODULES:
        path = os.path.join(_I18N_DIR, f"{module}.json")
        if not os.path.exists(path):
            logging.warning("[i18n] module file not found: %s", path)
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Warn on duplicate keys across modules
        dupes = set(merged) & set(data)
        if dupes:
            logging.warning("[i18n] duplicate keys across modules: %s", dupes)
        merged.update(data)
    _raw = merged
    return _raw


def load_strings(locale: str) -> dict:
    """Return {key: translated_string} for the given locale.

    Resolution: locale value → "en" fallback → "[key]" sentinel.
    """
    if locale not in _cache:
        all_t = _load_all()
        result = {}
        for key, values in all_t.items():
            val = values.get(locale) or values.get("en")
            result[key] = val if val is not None else f"[{key}]"
        _cache[locale] = result
    return _cache[locale]


def validate_translations(locales: tuple[str, ...] = ("en", "zh")) -> list[str]:
    """Return list of 'key.locale' pairs with missing values. Logs a warning if any."""
    all_t = _load_all()
    missing = [
        f"{key}.{loc}"
        for key, values in all_t.items()
        for loc in locales
        if not values.get(loc)
    ]
    if missing:
        logging.warning(
            "[i18n] %d missing translation(s): %s%s",
            len(missing),
            ", ".join(missing[:8]),
            " ..." if len(missing) > 8 else "",
        )
    return missing


def clear_i18n_cache() -> None:
    global _raw
    _raw = None
    _cache.clear()
