"""US-121 service 层 smoke 测试。跑法：python3 tests/test_services.py"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


def test_service_run_records_done():
    db.init_db()
    with db.service_run("pytest-svc") as run:
        run.tick(3)
    last = db.get_last_run("pytest-svc")
    assert last["status"] == "done"
    assert last["items_processed"] == 3
    assert last["stopped_early"] == 0
    assert last["duration_s"] is not None
    print("  ✅ 正常运行记 done + 处理数")


def test_service_run_records_failure_and_reraises():
    raised = False
    try:
        with db.service_run("pytest-svc-fail") as run:
            run.tick()
            raise RuntimeError("kaboom")
    except RuntimeError:
        raised = True
    assert raised, "异常必须重新抛出"
    last = db.get_last_run("pytest-svc-fail")
    assert last["status"] == "failed"
    assert "kaboom" in (last["error"] or "")
    print("  ✅ 异常记 failed 并重新抛")


def test_should_analyze_never_for_unknown_code():
    ok, reason = db.should_analyze("ZZZ_NONEXIST_CODE")
    assert ok is True and reason == "never"
    print("  ✅ 未分析过的股票 → (True, never)")


def test_select_returns_subset():
    codes = db.all_watched_codes()
    picked = db.select_codes_to_analyze(codes)
    assert len(picked) <= len(codes), "选出的不能多于总数"
    assert all(isinstance(t, tuple) and len(t) == 2 for t in picked)
    print(f"  ✅ 选择性筛选 {len(picked)}/{len(codes)}")


def test_stale_running_row_reaped_on_next_start():
    """US-139：GHA timeout 是 SIGKILL，finally 跑不到 → 记账里留永久 running。
    下次同服务启动必须收尸，否则「哪个服务掉链子」永远看不出来。"""
    from datetime import timedelta

    from radar_app.data.core import CN_TZ, get_conn
    from radar_app.data.services import STALE_RUN_HOURS

    db.init_db()
    stale = (datetime.now(CN_TZ) - timedelta(hours=STALE_RUN_HOURS + 1)).isoformat()
    fresh = datetime.now(CN_TZ).isoformat()
    with get_conn() as c:
        killed_id = c.execute(
            "INSERT INTO service_runs(service_name, started_at, status) "
            "VALUES('pytest-reap', :t, 'running') RETURNING id", {"t": stale},
        ).fetchone()["id"]
        # 同名但还新鲜的 running 不能被误杀（可能真在并行跑）
        spared_id = c.execute(
            "INSERT INTO service_runs(service_name, started_at, status) "
            "VALUES('pytest-reap', :t, 'running') RETURNING id", {"t": fresh},
        ).fetchone()["id"]
        # 别的服务的陈旧行也不能碰
        other_id = c.execute(
            "INSERT INTO service_runs(service_name, started_at, status) "
            "VALUES('pytest-reap-other', :t, 'running') RETURNING id", {"t": stale},
        ).fetchone()["id"]

    with db.service_run("pytest-reap"):
        pass

    with get_conn() as c:
        rows = {
            r["id"]: dict(r)
            for r in c.execute(
                "SELECT id, status, error FROM service_runs WHERE id IN "
                f"({killed_id}, {spared_id}, {other_id})"
            ).all()
        }
    assert rows[killed_id]["status"] == "killed", "陈旧 running 必须标 killed"
    assert "SIGKILL" in (rows[killed_id]["error"] or "")
    assert rows[spared_id]["status"] == "running", "新鲜 running 不能误杀"
    assert rows[other_id]["status"] == "running", "别的服务不能被牵连"
    print("  ✅ 陈旧 running 收尸，新鲜/异名不受影响")


if __name__ == "__main__":
    for fn in [
        test_service_run_records_done,
        test_service_run_records_failure_and_reraises,
        test_should_analyze_never_for_unknown_code,
        test_select_returns_subset,
        test_stale_running_row_reaped_on_next_start,
    ]:
        print(f"▶ {fn.__name__}")
        fn()
    print("\n✅ 全部通过")
