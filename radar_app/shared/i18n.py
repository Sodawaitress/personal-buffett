"""Shared i18n helpers."""

import json
import os

_I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "i18n")
_i18n_cache = {}


def load_strings(locale):
    if locale not in _i18n_cache:
        path = os.path.join(_I18N_DIR, f"{locale}.json")
        fallback = os.path.join(_I18N_DIR, "en.json")
        with open(path if os.path.exists(path) else fallback) as f:
            _i18n_cache[locale] = json.load(f)
    return _i18n_cache[locale]


def clear_i18n_cache():
    _i18n_cache.clear()
