"""Shared helpers for pipeline job lookups."""

import db


def get_recent_pending_job(code, minutes=15):
    with db.get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, status FROM pipeline_jobs
            WHERE code=? AND status IN ('pending','running')
              AND started_at > datetime('now', ?)
            ORDER BY id DESC LIMIT 1
            """,
            (code, f"-{minutes} minutes"),
        ).fetchone()
        return dict(row) if row else None
