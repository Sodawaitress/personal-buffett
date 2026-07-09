"""token-bucket 配速器测试。跑法：python3 tests/test_groq_ratelimit.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.groq_ratelimit import _Bucket, estimate_tokens, throttle


def test_estimate_monotonic():
    small = estimate_tokens("sys", "hi", 100)
    big = estimate_tokens("sys" * 100, "hi" * 500, 900)
    assert big > small, "更长的 prompt + 更大 max_tokens 应估更多 token"
    assert small >= 100, "至少覆盖 completion 预留"
    print(f"  ✅ estimate 单调: {small} < {big}")


def test_bucket_immediate_when_full():
    b = _Bucket(per_min=6000)  # 满桶
    waited = b.acquire(3000)
    assert waited == 0.0, "满桶取半应立即通过"
    print(f"  ✅ 满桶立即通过 waited={waited}")


def test_bucket_paces_when_drained():
    b = _Bucket(per_min=600)  # 10 tok/s
    b.acquire(600)            # 抽干
    t0 = time.monotonic()
    waited = b.acquire(20)   # 需补 20 tok → ~2s
    elapsed = time.monotonic() - t0
    assert 1.5 <= waited <= 3.0, f"抽干后应配速等待 ~2s，实际 {waited}"
    assert elapsed >= 1.5, "确实 sleep 了"
    print(f"  ✅ 抽干后配速 waited={waited:.2f}s")


def test_bucket_caps_oversized_request():
    b = _Bucket(per_min=1000)
    waited = b.acquire(999999)  # 超容量 → 截到容量，不会死循环
    assert waited == 0.0
    print("  ✅ 超容量请求被截断，不死循环")


def test_throttle_returns_wait():
    w = throttle("sys", "hi", 100)
    assert isinstance(w, float) and w >= 0
    print(f"  ✅ throttle 返回等待秒数 {w}")


if __name__ == "__main__":
    for fn in [
        test_estimate_monotonic,
        test_bucket_immediate_when_full,
        test_bucket_paces_when_drained,
        test_bucket_caps_oversized_request,
        test_throttle_returns_wait,
    ]:
        print(f"▶ {fn.__name__}")
        fn()
    print("\n✅ 全部通过")
