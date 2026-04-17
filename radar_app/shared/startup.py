"""Shared startup helpers for route and auth entrypoints."""

import db


def ensure_db_ready(run_migrations=True):
    db.init_db()
    if run_migrations:
        db._migrate()
