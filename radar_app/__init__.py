"""Application bootstrap helpers for the refactor branch."""

import logging
import os
import sys
import threading
import time

from dotenv import load_dotenv
from flask import Flask

from radar_app.data.core import teardown_request_conn
from radar_app.legacy.search_backend import warm_search_backend
from radar_app.context import register_context_processors
from radar_app.extensions import init_extensions
from radar_app.routes import register_routes
from radar_app.settings import load_settings

logger = logging.getLogger(__name__)

# 防止 Flask debug reloader 或多进程重复启动
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _seconds_until_next_run(hour: int = 16, minute: int = 30) -> float:
    """计算距离下一个北京时间 HH:MM 还有多少秒。"""
    from datetime import datetime, timedelta, timezone
    cn_tz = timezone(timedelta(hours=8))
    now = datetime.now(cn_tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    secs = (target - now).total_seconds()
    logger.info("[precursor_scheduler] 下次运行：北京时间 %02d:%02d，还有 %.0f 分钟",
                hour, minute, secs / 60)
    return secs


def _precursor_scheduler_loop():
    """
    后台守护线程：每天北京时间 16:30 精确触发。
    A股 15:00 收盘，数据源约 16:00 更新完毕，16:30 扫描拿到最新数据，
    17:30 Routine 跑时快照已就绪。
    """
    # 先等到下一个 16:30，避免启动时立刻跑
    time.sleep(_seconds_until_next_run(16, 30))
    while True:
        try:
            logger.info("[precursor_scheduler] 开始每日前兆信号扫描…")
            from scripts.precursor_scan import run_precursor_scan
            result = run_precursor_scan()
            logger.info("[precursor_scheduler] 完成: %s", result)
        except Exception as e:
            logger.warning("[precursor_scheduler] 扫描失败（不影响服务）: %s", e)

        try:
            logger.info("[precursor_scheduler] 开始每日摘要（GitHub快照）…")
            from scripts.daily_digest import run_daily_digest
            run_daily_digest()
        except Exception as e:
            logger.warning("[precursor_scheduler] 每日摘要失败（不影响服务）: %s", e)

        # 睡到明天 16:30
        time.sleep(_seconds_until_next_run(16, 30))


def _start_precursor_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    t = threading.Thread(target=_precursor_scheduler_loop, daemon=True, name="precursor-scheduler")
    t.start()
    logger.info("[precursor_scheduler] 后台调研扫描线程已启动（首次运行在 5 分钟后）")


def _prepare_runtime():
    root = os.path.dirname(os.path.dirname(__file__))
    scripts_dir = os.path.join(root, "scripts")
    if root not in sys.path:
        sys.path.insert(0, root)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    load_dotenv(os.path.join(root, ".env"))
    warm_search_backend()


def create_app():
    """Build the Flask app directly from the refactored module tree."""
    _prepare_runtime()
    import db

    db.init_db()
    db._migrate()
    db.expire_stale_jobs()
    from radar_app.shared.i18n import validate_translations
    validate_translations()
    settings = load_settings()
    root = os.path.dirname(os.path.dirname(__file__))

    app = Flask(
        __name__,
        template_folder=os.path.join(root, "templates"),
        static_folder=os.path.join(root, "static"),
    )
    app.secret_key = settings.secret_key
    app.teardown_appcontext(teardown_request_conn)
    bcrypt, oauth = init_extensions(app)
    register_context_processors(app)
    register_routes(app, bcrypt, oauth)

    # 启动每日前兆信号扫描（Fly.io 生产 + 本地 dev 均生效）
    _start_precursor_scheduler()

    return app


def run_dev_server(flask_app):
    """Preserve the current local startup behaviour behind the new entrypoint."""
    import db

    db.init_db()
    db.expire_stale_jobs()
    settings = load_settings()
    print(f"🚀 Personal Buffett → http://127.0.0.1:{settings.port} (debug={'on' if settings.debug else 'off'})")
    flask_app.run(debug=settings.debug, use_reloader=settings.debug, host="0.0.0.0", port=settings.port)
