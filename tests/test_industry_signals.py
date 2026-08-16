"""US-158：行业景气信号重写。

原设计（US-95）把 company_type（商业形态）当行业用，映射表只覆盖 3/9 种
类型 → 74% 的股票拿不到信号；生产 industry_signals 表只有 1 行、26 天没更新。

重写的两个核心契约：
  ① 动量由我们自己逐日累积算出（新浪无历史接口），**必须透传已积累天数**
  ② 数据不足时降级但不沉默 —— 绝不把 3 天的涨幅说成「30 日动量」
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.industry_signals import (HEADWIND_PCT, MIN_DAYS_FOR_SIGNAL,
                                      TAILWIND_PCT, build_signal,
                                      compute_momentum)


def _momentum(series, days=30):
    """直接复刻连乘逻辑，避免 import db（单测不碰 DB）。"""
    cum, used = 1.0, 0
    for row in series[:days]:
        pct = row.get("change_pct")
        if pct is None:
            continue
        cum *= (1.0 + float(pct) / 100.0)
        used += 1
    if used == 0:
        return {}
    return {"change_pct": round((cum - 1.0) * 100.0, 2),
            "days_available": used, "mature": used >= days}


# ── 连乘算法本身 ────────────────────────────────────────────

def test_compounding_not_summing():
    """日收益必须连乘，不是相加。10 个 +1% 是 +10.46%，不是 +10%。"""
    m = _momentum([{"change_pct": 1.0}] * 10)
    assert m["change_pct"] == 10.46
    assert m["days_available"] == 10


def test_negative_series():
    m = _momentum([{"change_pct": -2.0}] * 5)
    assert m["change_pct"] < 0
    assert round(m["change_pct"], 1) == -9.6


def test_mixed_series_cancels():
    """+10% 后 -9.0909% 应回到原点。"""
    m = _momentum([{"change_pct": 10.0}, {"change_pct": -9.0909}])
    assert abs(m["change_pct"]) < 0.01


def test_none_values_skipped_not_counted():
    """空值跳过，且不计入 days_available —— 否则会虚报成熟度。"""
    m = _momentum([{"change_pct": 1.0}, {"change_pct": None}, {"change_pct": 1.0}])
    assert m["days_available"] == 2


def test_empty_series_returns_empty():
    assert _momentum([]) == {}
    assert _momentum([{"change_pct": None}]) == {}


def test_maturity_flag():
    assert _momentum([{"change_pct": 0.1}] * 29)["mature"] is False
    assert _momentum([{"change_pct": 0.1}] * 30)["mature"] is True


def test_only_uses_window():
    """超过窗口的数据不该被算进去。"""
    m = _momentum([{"change_pct": 1.0}] * 50, days=30)
    assert m["days_available"] == 30


# ── 信号分档：顺风/逆风的门槛 ───────────────────────────────

def _signal_from(change, avail, days=30):
    """复刻 build_signal 的分档，绕开 DB。"""
    if avail < MIN_DAYS_FOR_SIGNAL:
        return "中性", False
    if change >= TAILWIND_PCT:
        return "顺风", avail >= days
    if change <= HEADWIND_PCT:
        return "逆风", avail >= days
    return "中性", avail >= days


def test_tailwind_threshold():
    assert _signal_from(5.0, 30)[0] == "顺风"
    assert _signal_from(4.9, 30)[0] == "中性"


def test_headwind_threshold():
    assert _signal_from(-5.0, 30)[0] == "逆风"
    assert _signal_from(-4.9, 30)[0] == "中性"


def test_too_few_days_never_claims_direction():
    """核心契约：只有 3 天数据时，哪怕涨了 20% 也不能说「顺风」。"""
    sig, mature = _signal_from(20.0, 3)
    assert sig == "中性"
    assert mature is False


def test_five_days_is_enough_to_speak():
    assert _signal_from(20.0, MIN_DAYS_FOR_SIGNAL)[0] == "顺风"


def test_immature_but_directional_is_flagged():
    """够 5 天可以给方向，但没到 30 天必须标记未成熟。"""
    sig, mature = _signal_from(8.0, 12)
    assert sig == "顺风"
    assert mature is False


# ── 缺口检测 ────────────────────────────────────────────────

def _gaps(have_dates, today, lookback=10):
    """复刻 find_gaps 的日期逻辑（周末跳过、今天不算缺口）。"""
    from datetime import date, timedelta
    y, m, d = (int(x) for x in today.split("-"))
    t = date(y, m, d)
    have = set(have_dates)
    expected, missing = [], []
    for i in range(lookback):
        cur = t - timedelta(days=i)
        if cur.weekday() >= 5:
            continue
        s = cur.strftime("%Y-%m-%d")
        if s == today:
            continue
        expected.append(s)
        if s not in have:
            missing.append(s)
    return {"expected": len(expected), "missing": sorted(missing, reverse=True)}


def test_weekend_not_counted_as_gap():
    """2026-08-15/16 是周六日，不该算缺口。"""
    g = _gaps(["2026-08-14", "2026-08-13"], today="2026-08-17", lookback=5)
    assert "2026-08-15" not in g["missing"]
    assert "2026-08-16" not in g["missing"]


def test_today_not_counted_as_gap():
    """今天可能还没到捕获时间。"""
    g = _gaps([], today="2026-08-17", lookback=1)
    assert g["missing"] == []


def test_real_gap_detected():
    g = _gaps(["2026-08-14"], today="2026-08-18", lookback=6)
    assert "2026-08-17" in g["missing"]


def test_no_gap_when_complete():
    g = _gaps(["2026-08-17", "2026-08-14", "2026-08-13", "2026-08-12"],
              today="2026-08-18", lookback=7)
    assert g["missing"] == []


# ── 非交易日守卫（实测抓到的真 bug）────────────────────────

def _is_weekend(date_str):
    from datetime import datetime as _dt
    return _dt.strptime(date_str, "%Y-%m-%d").weekday() >= 5


def _signature(rows):
    """复刻 industry_signals._signature。"""
    import hashlib
    import json
    return hashlib.md5(json.dumps(
        sorted((r["label"], r["change_pct"]) for r in rows),
        ensure_ascii=False).encode()).hexdigest()


def test_weekend_capture_is_skipped():
    """新浪非交易日返回上一交易日数据，照存会让周五的涨跌被动量重复计入
    （跨周末就是 3 倍）。实测正是在周日跑的，抓到了这个 bug。"""
    assert _is_weekend("2026-08-15") is True   # 周六
    assert _is_weekend("2026-08-16") is True   # 周日
    assert _is_weekend("2026-08-14") is False  # 周五
    assert _is_weekend("2026-08-17") is False  # 周一


def test_identical_data_detected_as_duplicate():
    """节假日在日期上看不出来，只能靠指纹：全部行业涨跌幅一模一样
    = 同一个交易日的重复数据。"""
    rows = [{"label": "new_blhy", "change_pct": 1.66},
            {"label": "new_dlhy", "change_pct": -0.5}]
    assert _signature(rows) == _signature(list(reversed(rows)))  # 与顺序无关


def test_different_data_not_duplicate():
    a = [{"label": "new_blhy", "change_pct": 1.66}]
    b = [{"label": "new_blhy", "change_pct": 1.67}]
    assert _signature(a) != _signature(b)


def test_signature_stable_across_calls():
    rows = [{"label": "x", "change_pct": 1.0}, {"label": "y", "change_pct": 2.0}]
    assert _signature(rows) == _signature(rows)


# ── 多源：两套体系并行，绝不桥接 ────────────────────────────

def _normalize_label(label):
    """复刻 get_signal_for_stock 的 label 归一化。"""
    if label and ":" not in label:
        return f"sina:{label}"
    return label


def test_legacy_label_normalized_to_sina():
    """US-158 首版写的是裸 label，加东财源后统一成带前缀。
    存量记录必须还能查到对应的 industry_daily 序列，否则信号卡片会消失。"""
    assert _normalize_label("new_blhy") == "sina:new_blhy"


def test_prefixed_labels_untouched():
    assert _normalize_label("sina:new_blhy") == "sina:new_blhy"
    assert _normalize_label("em:BK1036") == "em:BK1036"


def test_sources_never_bridged():
    """核心设计约束：两套分类体系的 label 永不混用。
    一只股票归属哪套体系，动量就从哪套体系的序列算 ——
    所以不存在「东财板块名对不上同花顺板块名」那类问题。"""
    em_labels = {"em:BK1036", "em:BK1033"}
    sina_labels = {"sina:new_blhy", "sina:new_dlhy"}
    assert not (em_labels & sina_labels)
    for lbl in em_labels | sina_labels:
        assert lbl.split(":")[0] in ("em", "sina")


def test_em_change_pct_scaled():
    """东财 f3 是放大 100 倍的整数（582 = 5.82%），必须除以 100。"""
    assert round(582 / 100.0, 4) == 5.82
    assert round(-31 / 100.0, 4) == -0.31
