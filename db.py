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


if __name__ == "__main__":
    init_db()
    print(f"DB ready: {DB_PATH}")
