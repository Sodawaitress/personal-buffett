"""
私人巴菲特 · 数据库层
兼容导出壳：实际实现已拆到 radar_app/data/
"""

from radar_app.data.analysis import *  # noqa: F401,F403
from radar_app.data.core import CN_TZ, DB_PATH, _migrate, get_conn, init_db
from radar_app.data.jobs import *  # noqa: F401,F403
from radar_app.data.market import *  # noqa: F401,F403
from radar_app.data.notifications import *  # noqa: F401,F403
from radar_app.data.portfolio import *  # noqa: F401,F403
from radar_app.data.stocks import *  # noqa: F401,F403
from radar_app.data.users import *  # noqa: F401,F403


# ── US-67 提问箱 ─────────────────────────────────────

def save_question(user_id, question, answer):
    with get_conn() as c:
        c.execute(
            "INSERT INTO user_questions (user_id, question, answer) VALUES (?,?,?)",
            (user_id, question, answer),
        )

def list_questions(limit=200):
    with get_conn() as c:
        rows = c.execute("""
            SELECT q.id, q.question, q.answer, q.created_at,
                   u.email, u.display_name
            FROM user_questions q
            LEFT JOIN users u ON u.id = q.user_id
            ORDER BY q.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def count_recent_questions(hours=24):
    with get_conn() as c:
        row = c.execute("""
            SELECT COUNT(*) FROM user_questions
            WHERE created_at > datetime('now', ?)
        """, (f"-{hours} hours",)).fetchone()
        return row[0] if row else 0


if __name__ == "__main__":
    init_db()
    print(f"DB ready: {DB_PATH}")
