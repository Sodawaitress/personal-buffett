"""Shared helpers for pipeline job lookups."""

from datetime import datetime, timezone, timedelta

import db


def get_recent_pending_job(code, minutes=15):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with db.get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, status FROM pipeline_jobs
            WHERE code=:code AND status IN ('pending','running')
              AND started_at > :cutoff
            ORDER BY id DESC LIMIT 1
            """,
            {"code": code, "cutoff": cutoff},
        ).fetchone()
        return dict(row) if row else None
