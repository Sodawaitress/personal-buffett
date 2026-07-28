"""US-138：机构雷达数值兜底。

回购进度 pct_done 为 NaN 时，format_institutional_section 曾抛
ValueError: cannot convert float NaN to integer —— 让 monolith 连崩 10 个交易日。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.institutional_radar import _safe_float, format_institutional_section

NAN = float("nan")

_QUOTES = {"600519": {"name": "贵州茅台", "price": 1500.0, "change": 1.2}}


def _section(**kw):
    """只喂被测那一块，其余给空 dict。"""
    args = dict(patterns={}, northbound_trend={}, restricted=[], quotes=_QUOTES,
                shareholder={}, repurchase={})
    args.update(kw)
    return format_institutional_section(**args)


# ── _safe_float ──────────────────────────────────────────────────────────────

def test_safe_float_normal():
    assert _safe_float(12.5) == 12.5
    assert _safe_float("3") == 3.0

def test_safe_float_nan_falls_back():
    assert _safe_float(NAN) == 0.0
    assert _safe_float(NAN, default=-1.0) == -1.0

def test_safe_float_inf_falls_back():
    assert _safe_float(float("inf")) == 0.0
    assert _safe_float(float("-inf")) == 0.0

def test_safe_float_none_and_garbage():
    assert _safe_float(None) == 0.0
    assert _safe_float("abc") == 0.0


# ── 回购进度：NaN / None / 正常 三态 ─────────────────────────────────────────

def test_repurchase_nan_does_not_crash():
    out = _section(repurchase={"600519": {"pct_done": NAN, "progress": "实施中"}})
    assert "nan" not in out.lower()

def test_repurchase_none_does_not_crash():
    out = _section(repurchase={"600519": {"pct_done": None, "progress": "实施中"}})
    assert "nan" not in out.lower()

def test_repurchase_normal_still_renders():
    out = _section(repurchase={"600519": {"pct_done": 45.0, "progress": "实施中"}})
    assert "已回购45%" in out
    assert "▓▓▓▓" in out

def test_repurchase_zero_pct_still_listed_when_in_progress():
    # pct_done=0 但进度含「实施」仍应上榜（原过滤逻辑意图）
    out = _section(repurchase={"600519": {"pct_done": 0.0, "progress": "实施中"}})
    assert "贵州茅台" in out


# ── 股东人数：同一类 NaN 兜底 ────────────────────────────────────────────────

def test_shareholder_nan_filtered_out():
    out = _section(shareholder={"600519": {"pct_change": NAN, "cnt": 100000,
                                           "quarter": "20254", "signal": "筹码集中"}})
    assert "nan" not in out.lower()

def test_shareholder_normal_still_renders():
    out = _section(shareholder={"600519": {"pct_change": -15.0, "cnt": 100000,
                                           "quarter": "20254", "signal": "筹码集中"}})
    assert "-15.0%" in out


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
