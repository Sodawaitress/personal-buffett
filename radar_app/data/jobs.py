"""Pipeline job queries."""

from radar_app.data.core import get_conn


def create_job(user_id, code, job_type):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO pipeline_jobs(user_id,code,job_type,status,started_at)
            VALUES(?,?,?,'pending',datetime('now'))
        """,
            (user_id, code, job_type),
        )
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_job(job_id, status, log=None, error=None):
    finished = "datetime('now')" if status in ("done", "failed") else "NULL"
    with get_conn() as c:
        c.execute(
            f"""
            UPDATE pipeline_jobs
            SET status=?, log=COALESCE(?,log),
                error=COALESCE(?,error),
                finished_at=({finished})
            WHERE id=?
        """,
            (status, log, error, job_id),
        )


def get_job(job_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM pipeline_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def expire_stale_jobs(max_age_minutes=120):
    with get_conn() as c:
        c.execute(
            """
            UPDATE pipeline_jobs
            SET status='failed', error='超时自动终止（超过 {}分钟未完成）'
            WHERE status IN ('running','pending')
              AND started_at < datetime('now', '-{} minutes')
        """.format(max_age_minutes, max_age_minutes)
        )
