"""App settings helpers."""

import os
from dataclasses import dataclass


def env_flag(name, default="1"):
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class AppSettings:
    secret_key: str
    port: int
    debug: bool


def load_settings():
    return AppSettings(
        secret_key=os.environ.get("FLASK_SECRET_KEY", "personal-buffett-2024-xK9m"),
        port=int(os.environ.get("PORT", 5001)),
        debug=env_flag("FLASK_DEBUG", "1"),
    )
