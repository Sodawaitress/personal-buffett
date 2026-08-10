"""US-140：Groq 429 兜底必须让位于调用方的时间预算。

单只内部 sleep(450s) 会绕过「每只之间」的 deadline 检查 —— material scan 的
20 分钟预算实测跑成 60 分钟被 SIGKILL，就是这么来的。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts import buffett_groq


class _Resp429:
    status_code = 429

    def __init__(self, wait="450"):
        self.headers = {"retry-after": wait}


def _patched_call(resp, deadline, monkey_sleep):
    """跑一次 _call_groq，桩掉网络/配速/sleep，返回 (结果, 是否睡过)。"""
    orig = (buffett_groq.requests.post, buffett_groq.throttle,
            buffett_groq.time.sleep, buffett_groq.GROQ_API_KEY)
    slept = []
    buffett_groq.requests.post = lambda *a, **k: resp
    buffett_groq.throttle = lambda *a, **k: 0
    buffett_groq.time.sleep = lambda s: slept.append(s)
    buffett_groq.GROQ_API_KEY = "test-key"
    buffett_groq.set_call_deadline(deadline)
    try:
        out = buffett_groq._call_groq("sys", "user", max_tokens=10)
    finally:
        buffett_groq.set_call_deadline(None)
        (buffett_groq.requests.post, buffett_groq.throttle,
         buffett_groq.time.sleep, buffett_groq.GROQ_API_KEY) = orig
    return out, slept


def test_gives_up_when_sleep_would_exceed_deadline():
    # 预算只剩 10 秒，429 要等 450 秒 → 必须直接放弃，一秒都不许睡
    out, slept = _patched_call(_Resp429("450"), time.time() + 10, True)
    assert out == "", "超预算时应返回空串让调用方降级"
    assert slept == [], f"不该睡，实际睡了 {slept}"


def test_sleeps_when_deadline_allows():
    # 预算还剩 1 小时，450 秒睡得起 → 保持原行为（重试）
    out, slept = _patched_call(_Resp429("450"), time.time() + 3600, True)
    assert slept, "预算充裕时应照常等待重试"
    assert slept[0] >= 450


def test_no_deadline_keeps_original_behaviour():
    # 没设 deadline 的调用方（网页端即时请求）行为不变
    out, slept = _patched_call(_Resp429("450"), None, True)
    assert slept, "未设预算时应维持原有 Retry-After 等待"


def test_set_and_clear_deadline():
    buffett_groq.set_call_deadline(12345.0)
    assert buffett_groq._call_deadline == 12345.0
    buffett_groq.set_call_deadline(None)
    assert buffett_groq._call_deadline is None


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✓  {name}")
                passed += 1
            except Exception as e:
                print(f"  ✗  {name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
