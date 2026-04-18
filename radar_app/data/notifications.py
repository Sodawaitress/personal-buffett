"""Notification queries."""

from datetime import datetime, timedelta, timezone

from radar_app.data.core import get_conn


def check_poor_rating_streak(code: str, user_id: int) -> list:
    with get_conn() as c:
        row = c.execute("SELECT status FROM user_watchlist WHERE user_id=? AND stock_code=?", (user_id, code)).fetchone()
        if not row or row["status"] == "holding":
            return []

        rows = c.execute(
            """
            SELECT grade FROM analysis_results
            WHERE code=? AND period='daily' AND grade IS NOT NULL
            ORDER BY id DESC LIMIT 6
        """,
            (code,),
        ).fetchall()

        if len(rows) < 6:
            return []

        poor = {"d", "d-"}
        grades = [r["grade"] for r in rows]
        return grades if all(g.lower() in poor for g in grades) else []


def create_notification(user_id: int, code: str, grades: list):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_conn() as c:
        existing = c.execute(
            """
            SELECT id FROM user_notifications
            WHERE user_id=? AND code=? AND type='poor_rating'
              AND dismissed_at IS NULL
              AND (snoozed_until IS NULL OR snoozed_until < ?)
        """,
            (user_id, code, today),
        ).fetchone()
        if existing:
            return
        msg = f"该股票最近6次评级均为 D 级：{', '.join(grades)}"
        c.execute(
            """
            INSERT INTO user_notifications(user_id, code, type, message)
            VALUES (?, ?, 'poor_rating', ?)
        """,
            (user_id, code, msg),
        )


def get_active_notifications(user_id: int) -> list:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT n.id, n.code, n.type, n.message, n.created_at,
                   s.name AS stock_name
            FROM user_notifications n
            LEFT JOIN stocks s ON s.code = n.code
            WHERE n.user_id=? AND n.dismissed_at IS NULL
              AND (n.snoozed_until IS NULL OR n.snoozed_until < ?)
            ORDER BY n.created_at DESC
        """,
            (user_id, today),
        ).fetchall()
        return [dict(r) for r in rows]


def snooze_notification(notif_id: int, user_id: int):
    until = (datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%d")
    with get_conn() as c:
        c.execute("UPDATE user_notifications SET snoozed_until=? WHERE id=? AND user_id=?", (until, notif_id, user_id))


def dismiss_notification(notif_id: int, user_id: int):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as c:
        c.execute("UPDATE user_notifications SET dismissed_at=? WHERE id=? AND user_id=?", (now, notif_id, user_id))
