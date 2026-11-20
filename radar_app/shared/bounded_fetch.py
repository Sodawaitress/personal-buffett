"""给请求路径上的外网抓取加护栏：缓存 + 单飞 + 等待上限。

背景（2026-11-20 事故）：首页每次渲染都同步抓 FOMC / RSS / yfinance，而 feedparser.parse(url)
没有超时。gunicorn 只有 1 worker × 4 threads，几次外网卡住就把线程占满，/healthz 也答不了，
Fly 判定实例不健康，整站 503 了 16 分钟。

做法：
- 结果按 key 缓存 ttl 秒；过期后由后台线程刷新，同一 key 同时只会有一个刷新在跑。
- 请求线程最多等 wait 秒；等不到就返回上一次的结果（没有就返回 fallback）。
- 抓取线程是 daemon，就算外网永远不回，也只占住一个后台线程，不占请求线程。
"""

import functools
import threading
import time

_lock = threading.Lock()
_cache = {}      # key -> (expires_at, value)
_inflight = {}   # key -> threading.Event


def _refresh(key, fn, ttl, done):
    try:
        value = fn()
        with _lock:
            _cache[key] = (time.monotonic() + ttl, value)
    except Exception:
        pass
    finally:
        with _lock:
            _inflight.pop(key, None)
        done.set()


def bounded_cached(key, fn, *, ttl, wait, fallback):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        done = _inflight.get(key)
        if done is None:
            done = threading.Event()
            _inflight[key] = done
            threading.Thread(target=_refresh, args=(key, fn, ttl, done), daemon=True,
                             name=f"bounded-fetch:{key}").start()
    done.wait(wait)
    with _lock:
        hit = _cache.get(key)
    if hit:
        return hit[1]
    return fallback() if callable(fallback) else fallback


def bounded(ttl, wait, fallback):
    """装饰器版本；缓存 key = 函数名 + 参数。"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__module__, fn.__name__, args, tuple(sorted(kwargs.items())))
            return bounded_cached(key, lambda: fn(*args, **kwargs), ttl=ttl, wait=wait, fallback=fallback)
        wrapper.__wrapped_unbounded__ = fn
        return wrapper
    return deco


def _reset_for_tests():
    with _lock:
        _cache.clear()
        _inflight.clear()
