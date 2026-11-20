"""2026-11-20 事故回归：页面请求里的外网抓取不能把请求线程挂住。"""

import threading
import time

import pytest

from radar_app.shared import bounded_fetch
from radar_app.shared.bounded_fetch import bounded, bounded_cached


@pytest.fixture(autouse=True)
def _clean():
    bounded_fetch._reset_for_tests()
    yield
    bounded_fetch._reset_for_tests()


def test_hanging_fetch_returns_fallback_within_wait():
    release = threading.Event()
    t0 = time.monotonic()
    out = bounded_cached("hang", lambda: release.wait(30) or ["late"], ttl=60, wait=0.2, fallback=list)
    assert out == []
    assert time.monotonic() - t0 < 1
    release.set()


def test_only_one_inflight_fetch_per_key():
    calls = []
    release = threading.Event()

    def slow():
        calls.append(1)
        release.wait(5)
        return ["ok"]

    for _ in range(5):
        bounded_cached("k", slow, ttl=60, wait=0.05, fallback=list)
    assert len(calls) == 1
    release.set()
    time.sleep(0.1)
    assert bounded_cached("k", slow, ttl=60, wait=0.05, fallback=list) == ["ok"]
    assert len(calls) == 1


def test_cache_hit_and_stale_served_while_refreshing():
    n = {"v": 0}

    @bounded(ttl=0.05, wait=1, fallback=list)
    def f():
        n["v"] += 1
        return [n["v"]]

    assert f() == [1]
    assert f() == [1]
    time.sleep(0.1)
    assert f() == [2]


def test_exception_gives_fallback():
    def boom():
        raise RuntimeError("x")
    assert bounded_cached("e", boom, ttl=60, wait=1, fallback=dict) == {}


def test_dashboard_adapters_are_bounded(monkeypatch):
    import os, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.syspath_prepend(os.path.join(root, "scripts"))
    from radar_app.legacy import market_data
    for name in ("fetch_cn_market_news", "fetch_fomc_news", "fetch_nz_market_news",
                 "fetch_rbnz_news", "fetch_nzx50"):
        assert hasattr(getattr(market_data, name), "__wrapped_unbounded__"), name
