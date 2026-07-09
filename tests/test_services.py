"""US-121 service 层 smoke 测试。跑法：python3 tests/test_services.py"""
import os
import sys

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


if __name__ == "__main__":
    for fn in [
        test_service_run_records_done,
        test_service_run_records_failure_and_reraises,
        test_should_analyze_never_for_unknown_code,
        test_select_returns_subset,
    ]:
        print(f"▶ {fn.__name__}")
        fn()
    print("\n✅ 全部通过")
