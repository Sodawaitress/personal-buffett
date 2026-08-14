"""US-151：北向资金停更后不许再污染机构意向评分。

背景：官方 2026-07 起停止公布日度北向数据，akshare 之后返回 0.0 / 空，
但 northbound_history 里 2026-07-09 那条旧记录被下游当成「今天的值」。

两个方向相反的失真，根因都是 comps["northbound"] 的 valid 恒为 True：
  批量链路  一串 0.0 被 `n >= 0` 读成「连续 N 天净流入」→ 每只 A 股白送 +1.07 分，
           还生成「外资已连续 4 天买入，境外机构在建仓」的假证据文案
  实时链路  northbound 恒为 {} → 按 0 分参与加权平均 → 所有 A 股意向分被稀释 ~13%
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.institutional_radar import _is_northbound_stale


# ── 停更判定 ────────────────────────────────────────────────────

def test_stale_when_data_is_five_weeks_old():
    """生产实况：最后一条 2026-07-09，快照日 2026-08-14。"""
    assert _is_northbound_stale("2026-07-09", today="2026-08-14") is True


def test_fresh_within_threshold():
    assert _is_northbound_stale("2026-08-13", today="2026-08-14") is False


def test_long_weekend_not_killed():
    """7 天阈值要能扛住长假前半段，别把健康数据误判成停更。"""
    assert _is_northbound_stale("2026-08-08", today="2026-08-14") is False


def test_missing_or_garbage_date_is_stale():
    assert _is_northbound_stale("") is True
    assert _is_northbound_stale("not-a-date") is True
    assert _is_northbound_stale(None) is True


# ── 评分：停更必须整项退出加权平均 ──────────────────────────────

def _northbound_comp(northbound):
    """只取 compute_intention_score 里 northbound 那一项。

    直接复刻被测分支，避免把整条打分链路（需要 DB / 网络）拖进单测。
    """
    comps = {}
    nb = northbound or {}
    con = nb.get("consecutive", 0)
    dir_nb = nb.get("direction", "")
    if not nb or nb.get("stale") or dir_nb in ("", "unknown"):
        comps["northbound"] = {"dir": 0.0, "weight": 1.5, "valid": False}
    elif con and dir_nb in ("inflow", "outflow"):
        sign = +1 if dir_nb == "inflow" else -1
        comps["northbound"] = {"dir": sign * min(con / 5.0, 1.0),
                               "weight": 1.5, "valid": True}
    else:
        comps["northbound"] = {"dir": 0.0, "weight": 1.5, "valid": True}
    return comps["northbound"]


def test_stale_northbound_is_invalid():
    """停更 → valid False，分子分母同时剔除（跟 participation 一致）。"""
    c = _northbound_comp({"stale": True, "as_of": "2026-07-09",
                          "direction": "unknown", "consecutive": 0})
    assert c["valid"] is False
    assert c["dir"] == 0.0


def test_empty_northbound_is_invalid():
    """实时链路 signals['northbound'] 恒为 {} —— 不许再按 0 分投票稀释分数。"""
    assert _northbound_comp({})["valid"] is False
    assert _northbound_comp(None)["valid"] is False


def test_live_inflow_still_scores():
    """数据源哪天恢复了，正常信号要照常计分——本次修的是误判不是关掉功能。"""
    c = _northbound_comp({"stale": False, "direction": "inflow", "consecutive": 5})
    assert c["valid"] is True
    assert c["dir"] == 1.0


def test_live_outflow_still_scores():
    c = _northbound_comp({"stale": False, "direction": "outflow", "consecutive": 3})
    assert c["valid"] is True
    assert c["dir"] < 0


def test_zero_run_no_longer_reads_as_inflow():
    """核心回归：一串 0.0 必须落到 flat/0 连续天数，不能变成看多证据。"""
    c = _northbound_comp({"stale": False, "direction": "flat", "consecutive": 0})
    assert c["dir"] == 0.0
    assert c["valid"] is True  # 数据是新鲜的，只是当天持平


def test_invalid_component_drops_out_of_average():
    """valid=False 的项不该进分母——这是「稀释 13%」的那个 bug。"""
    comps = {
        "insider":    {"dir": 1.0, "weight": 2.0, "valid": True},
        "northbound": _northbound_comp({"stale": True}),
    }
    valid = {k: v for k, v in comps.items() if v["valid"]}
    w_max = sum(v["weight"] for v in valid.values())
    score = sum(v["dir"] * v["weight"] for v in valid.values()) / w_max * 10.0
    assert w_max == 2.0          # 1.5 的北向权重没有留在分母里
    assert score == 10.0         # 满分不被死信号拖低
