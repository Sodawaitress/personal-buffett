"""US-167：机构调研是「注意力」信号，不是「方向」信号。

## 用户在微信里提的问题（2026-08-24）

> 这个机构接连两个月调研的红柱子，但是它的股价还是在跌，说明机构调研的时候
> 不一定马上就涨，值得关注，**或者说调研到最后并不值得机构买，也不一定**

她说对了系统做错的事。调研在两处被写死成单向看涨：
    _SIGNAL_DEFS["survey_visit"] = {"direction": "bull", "weight": 2}
    意向分  dir_v = min(sv_score / 30.0, 1.0)    # 恒为正
**系统里没有任何路径能表达「机构去看了，然后决定不买」。**

本仓第三次犯同一类错（无方向的量被贴方向标签）：北向 0.0 当成连续买入、
前兆分 abs(融券) 当成「机构在悄悄建仓」、调研当成无条件看涨。

## 做法：不猜方向，查后续
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.survey_followthrough import (FOLLOW_DAYS, _MIN_DECIDED, build,
                                          classify)


def _lk(prices):
    return lambda d: prices.get(d)


# ── 三态分档 ────────────────────────────────────────────

def test_classify_thresholds():
    assert classify(3.0) == "followed_up"
    assert classify(-3.0) == "followed_down"
    assert classify(2.9) == "no_follow"
    assert classify(-2.9) == "no_follow"
    assert classify(None) is None


def test_threshold_is_not_too_tight():
    """A 股日常波动大，±3% 以内必须算「没动」——阈值太小会把噪音判成方向。"""
    assert classify(1.5) == "no_follow"


# ── 核心：用户描述的那个场景 ──────────────────────────────

def test_surveyed_twice_but_price_fell():
    """「接连两个月调研的红柱子，股价还是在跌」——必须能说出「看完没买」。"""
    prices = {"2026-06-10": 40.0, "2026-06-30": 36.0,
              "2026-07-15": 38.0, "2026-08-04": 34.0}
    ev = [{"date": "2026-06-10", "n_inst": 12, "is_specific": True},
          {"date": "2026-07-15", "n_inst": 8, "is_specific": True}]
    r = build(ev, _lk(prices), today="2026-08-24")
    assert r["direction"] == "bear"
    assert "看完没买" in r["headline"]
    assert r["summary"]["down"] == 2


def test_surveyed_and_price_rose():
    prices = {"2026-06-10": 30.0, "2026-06-30": 34.0,
              "2026-07-15": 34.0, "2026-08-04": 39.0}
    ev = [{"date": "2026-06-10", "n_inst": 12, "is_specific": True},
          {"date": "2026-07-15", "n_inst": 8, "is_specific": True}]
    r = build(ev, _lk(prices), today="2026-08-24")
    assert r["direction"] == "bull"
    assert "买了" in r["headline"]


# ── 样本量纪律 ──────────────────────────────────────────

def test_single_decided_event_gives_no_direction():
    """实测踩到的：n=1 时原逻辑输出「1 次里 1 次之后反而跌了 —— 看完没买，
    甚至在卖」。一次巧合被讲成规律，太重了。"""
    prices = {"2026-06-10": 40.0, "2026-06-30": 36.0}
    r = build([{"date": "2026-06-10", "n_inst": 12, "is_specific": True}],
              _lk(prices), today="2026-08-24")
    assert r["direction"] is None
    assert "样本太少" in r["headline"]
    assert _MIN_DECIDED == 2


def test_all_pending_says_so():
    r = build([{"date": "2026-08-22", "n_inst": 5, "is_specific": True}],
              _lk({}), today="2026-08-24")
    assert r["direction"] is None
    assert r["summary"]["pending"] == 1


def test_low_confidence_flagged():
    """非专项调研本地回测只有 50% 上涨（抛硬币），必须标信心低。"""
    prices = {"2026-06-10": 40.0, "2026-06-30": 36.0,
              "2026-07-15": 38.0, "2026-08-04": 34.0}
    ev = [{"date": "2026-06-10", "n_inst": 3, "is_specific": False},
          {"date": "2026-07-15", "n_inst": 2, "is_specific": False}]
    r = build(ev, _lk(prices), today="2026-08-24")
    assert r["confidence"] == "low"
    assert "样本少" in r["headline"]


def test_specific_surveys_take_precedence():
    """本地回测：专项调研上涨 72%，其他调研 50%。所以方向只由专项调研决定，
    普通调研只计入「有人在看」。"""
    prices = {"2026-06-10": 30.0, "2026-06-30": 34.0,   # 专项 → 涨
              "2026-07-01": 40.0, "2026-07-21": 34.0,   # 普通 → 跌
              "2026-07-05": 40.0, "2026-07-25": 34.0}   # 普通 → 跌
    ev = [{"date": "2026-06-10", "n_inst": 12, "is_specific": True},
          {"date": "2026-07-01", "n_inst": 2, "is_specific": False},
          {"date": "2026-07-05", "n_inst": 2, "is_specific": False}]
    r = build(ev, _lk(prices), today="2026-08-24")
    # 专项只有 1 条 → 样本不足，不给方向（而不是被两条普通调研带成 bear）
    assert r["direction"] is None


# ── 健壮性 ──────────────────────────────────────────────

def test_no_events():
    r = build([], _lk({}), today="2026-08-24")
    assert r["direction"] is None and r["events"] == []


def test_bad_dates_skipped():
    r = build([{"date": "not-a-date"}, {}, {"date": "2026-99-99"}],
              _lk({}), today="2026-08-24")
    assert r["events"] == []


def test_future_event_skipped():
    r = build([{"date": "2026-09-01", "n_inst": 5}], _lk({}), today="2026-08-24")
    assert r["events"] == []


def test_missing_price_says_so_instead_of_blaming_recency():
    """查不到当时的价格就说查不到，**不能拿今天的价格硬算**（US-155 的教训），
    **也不能说成「还太新」**（US-176）。

    生产实拍：锐科激光 07-09 的调研在 08-25 的页面上显示「还太新，看不出」——
    那是 **47 天前**，20 天观察窗早走完了。真正缺的是价格数据。
    说成「太新」不只是措辞不准，它指错了方向：用户会以为再等几天就有了。
    """
    r = build([{"date": "2026-06-10", "n_inst": 5, "is_specific": True}],
              _lk({}), today="2026-08-24")
    assert r["events"][0]["outcome"] == "no_price"
    assert r["events"][0]["pct"] is None
    assert "查不到" in r["events"][0]["label"]
    assert "太新" not in r["headline"]


def test_genuinely_new_event_still_says_too_new():
    """真·太新的事件仍然说「太新」—— 两种原因要分得开，不是把一种改成另一种。"""
    r = build([{"date": "2026-08-22", "n_inst": 5, "is_specific": True}],
              _lk({}), today="2026-08-24")
    assert r["events"][0]["outcome"] == "pending"
    assert "太新" in r["headline"]


def test_events_sorted_newest_first():
    prices = {"2026-06-10": 40.0, "2026-06-30": 36.0,
              "2026-07-15": 38.0, "2026-08-04": 34.0}
    ev = [{"date": "2026-06-10", "n_inst": 1, "is_specific": True},
          {"date": "2026-07-15", "n_inst": 1, "is_specific": True}]
    r = build(ev, _lk(prices), today="2026-08-24")
    assert r["events"][0]["date"] > r["events"][1]["date"]


def test_follow_window_is_about_14_trading_days():
    assert FOLLOW_DAYS == 20        # 20 自然日 ≈ 14 交易日


# ── 前端必须显示它 ──────────────────────────────────────

def test_template_renders_followthrough():
    root = os.path.join(os.path.dirname(__file__), '..')
    tpl = open(os.path.join(root, 'templates/stock/signals.html')).read()
    assert 'survey_followthrough' in tpl
    assert 'svft' in tpl
    # 必须紧跟在柱状图之后 —— 用户正是盯着柱子问「然后呢」
    assert tpl.index('svchart') < tpl.index('svft')


# ── 信号层：调研不再是写死的看涨 ─────────────────────────

def test_signal_defs_survey_is_attention_not_bull():
    """本仓第三次栽在「无方向的量被贴方向标签」上。这条测试钉住调研这次。"""
    from radar_app.data.signal_events import _SIGNAL_DEFS
    assert _SIGNAL_DEFS["survey_visit"]["direction"] == "attention"
    assert _SIGNAL_DEFS["survey_active"]["direction"] == "attention"


def test_attention_does_not_join_resonance():
    """attention 不能被算进多空共振——否则「看空在撤 + 机构在建仓」的
    自相矛盾又会回来（小商品城，用户妈妈 2026-08-24 提的）。"""
    from radar_app.data.signal_events import _calc_resonance
    r = _calc_resonance([
        {"key": "survey_visit", "direction": "attention", "weight": 2},
        {"key": "short_up",     "direction": "bear",      "weight": 2},
    ])
    assert r["bull_count"] == 0
    assert r["direction"] != "bull"


def test_survey_direction_falls_back_to_none_on_error():
    """推不出方向就保持 attention，绝不猜。"""
    from radar_app.data.signal_events import _survey_direction
    assert _survey_direction("000000", {})[0] is None
    assert _survey_direction("000000", {"events": []})[0] is None


def test_presenter_and_signals_share_one_judge():
    """页面上那段「调研之后发生了什么」和榜单上的方向必须同源，
    否则同一只股票会在两个地方说两套话。"""
    import inspect

    from radar_app.data import signal_events
    from radar_app.stocks import presenter
    for mod in (signal_events, presenter):
        src = inspect.getsource(mod)
        assert "from scripts.survey_followthrough import build" in src
