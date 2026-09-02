"""US-207：DDL 必须串行化，否则并发跑就会死锁。

2026-09-02 pipeline 的 market 一棒挂了：

    [SQL: CREATE INDEX IF NOT EXISTS idx_precursor_history_code ...]
    psycopg2.errors.DeadlockDetected
    Process 25788 waits for ShareLock on relation 24992
    Process 26949 waits for RowExclusiveLock on relation 24957

原因朴素：`init_db()` 每次发 59 条 DDL，仓里 28 处在调它 —— 每个
`svc_*.py` 启动都调，Fly 上的 web 应用启动也调。DDL 拿重锁，
两个进程一交叉，获取顺序就反了。

> **「幂等」只保证结果一样，不保证并发安全。**
> `CREATE TABLE IF NOT EXISTS` 重复跑不会出错，但两个进程同时跑会互相锁死。

顾问锁是 Postgres 上处理并发迁移的标准做法。SQLite 单写者，走 no-op。
"""
import inspect

from radar_app.data import core as db


def test_init_db_and_migrate_both_take_the_ddl_lock():
    """守接线：两个发 DDL 的入口都必须在锁里。
    只锁一个等于没锁 —— 另一个照样能和它交叉。"""
    for fn in (db.init_db, db._migrate):
        src = inspect.getsource(fn)
        assert "_ddl_lock()" in src, f"{fn.__name__} 没有串行化，会和别人死锁"


def test_lock_is_held_on_one_connection_not_per_statement():
    """顾问锁挂在会话上。用 `engine.begin()` 每条语句一个事务的话，
    会话一结束锁就自动放了 —— 看着有锁，实际没锁。"""
    src = inspect.getsource(db._ddl_lock)
    assert "eng.connect()" in src, "锁没有挂在一条长连接上"
    assert "pg_advisory_lock" in src and "pg_advisory_unlock" in src


def test_sqlite_skips_the_lock():
    """SQLite 没有 pg_advisory_lock，也不需要 —— 它是单写者。
    不跳过的话本地和测试会直接报语法错。"""
    src = inspect.getsource(db._ddl_lock)
    assert 'dialect.name != "postgresql"' in src, "SQLite 上会去调 pg_ 函数"


def test_unlock_survives_an_exception():
    """DDL 中途抛异常时锁必须放掉，否则整条流水线后面全卡死 ——
    比原本的死锁更糟：死锁至少会被 Postgres 检测并终止一方。"""
    src = inspect.getsource(db._ddl_lock)
    assert "finally:" in src, "异常路径没有释放锁"
    assert src.index("yield") < src.index("finally:")


def test_migrations_still_work_end_to_end():
    """锁加上之后，建表和加列本身没坏。"""
    db.init_db()
    db._migrate()
    with db.get_engine().begin() as conn:
        conn.execute(db.text("SELECT 1"))
