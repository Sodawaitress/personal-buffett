"""Pipeline job queries."""

from datetime import datetime, timedelta, timezone

from radar_app.data.core import get_conn


def create_job(user_id, code, job_type):
    with get_conn() as c:
        row = c.execute(
            """
            INSERT INTO pipeline_jobs(user_id,code,job_type,status,started_at)
            VALUES(:user_id,:code,:job_type,'pending',CURRENT_TIMESTAMP)
            RETURNING id
            """,
            {"user_id": user_id, "code": code, "job_type": job_type},
        ).fetchone()
        return row["id"]


def update_job(job_id, status, log=None, error=None):
    # CURRENT_TIMESTAMP is SQL standard; works in SQLite and PostgreSQL.
    finished = "CURRENT_TIMESTAMP" if status in ("done", "failed") else "NULL"
    with get_conn() as c:
        c.execute(
            f"UPDATE pipeline_jobs SET status=:status, log=COALESCE(:log,log), "
            f"error=COALESCE(:error,error), finished_at=({finished}) WHERE id=:id",
            {"status": status, "log": log, "error": error, "id": job_id},
        )


def get_job(job_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM pipeline_jobs WHERE id=:id", {"id": job_id}
        ).fetchone()
        return dict(row) if row else None


def expire_stale_jobs(max_age_minutes=120):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
    with get_conn() as c:
        c.execute(
            "UPDATE pipeline_jobs SET status='failed', error=:error "
            "WHERE status IN ('running','pending') AND started_at < :cutoff",
            {"error": f"超时自动终止（超过{max_age_minutes}分钟未完成）", "cutoff": cutoff},
        )
