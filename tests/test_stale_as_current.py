"""US-177：把「过去发生过的事」讲成「现在的状态」。

## 妈妈实拍的两条，是同一个病

**① 中石科技 300684 —— 推送说「股价还没反应」**

> 「都长成这样了，他说股价还没反应」

推送原文：「机构在悄悄研究/建仓，**股价还没反应** → 最早的领先信号」。
而它 4 个月里从 41 涨到 97（当时 86）—— **翻了一倍多**。

`smart_money_vs_price` 只看 **近 5 日**（`_price_5d`）。一只翻倍的股票在
任意 5 天里都可能微跌，于是系统在最不该喊「还没涨」的时候喊了「还没涨」，
**而且是朝着让人买入的方向喊**。

**② 奥来德 688378 —— 「近半年内部人净买入」**

> 「这个内部人士买入是 4 月」「这个信息就太滞后了」「这个滞后的消息没有意义」

卡片没撒谎（确实在「近半年」窗口内），但**「近半年内部人净买入」读起来
是现在的状态**，而它描述的是四个月前的动作 —— 这 4 个月里股价从 ~24 涨到
62.89 又跌回 42.22。而且列表按**重要性**排序、不按时间，所以她得自己一条条
看日期才发现。

## 共同的病根

**时间窗口只用来「取数据」，没用来「限定说法」。**

「近半年有过」和「现在正在」是两件事。系统用前者的数据，说了后者的话。
这和本仓反复栽的「无方向的量贴方向标签」是同一族错误 ——
都是**把一个受限的观测，讲成一个不受限的结论**。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


# ── ① 「股价还没反应」要过长窗口的闸 ────────────────────

def _lead(p60, p5, direction="bull", count=3):
    import radar_app.data.signal_events as se
    old_long, old_5 = se._price_change_over, se._price_5d
    se._price_change_over = lambda code, days: p60
    se._price_5d = lambda code: p5
    try:
        return se.smart_money_vs_price("TEST", {"direction": direction,
                                                "resonance_count": count})
    finally:
        se._price_change_over, se._price_5d = old_long, old_5


def test_already_doubled_stock_is_not_called_unreacted():
    """中石科技那一条。60 日已涨 40%，就算最近 5 日微跌，也不能说「还没反应」。"""
    assert _lead(p60=40.0, p5=-3.0) is None


def test_genuinely_flat_stock_still_gets_the_lead_signal():
    """真·没反应的仍要报 —— 这个信号本身是有价值的，不能一刀切掉。"""
    assert _lead(p60=2.0, p5=-3.0) == "lead_bull"


def test_threshold_is_at_twenty_percent():
    assert _lead(p60=19.0, p5=-3.0) == "lead_bull"
    assert _lead(p60=21.0, p5=-3.0) is None


def test_bear_side_is_symmetric():
    """已经跌透的股票，不能说「机构在撤、股价还没跌」。"""
    assert _lead(p60=-35.0, p5=3.0, direction="bear") is None
    assert _lead(p60=-2.0, p5=3.0, direction="bear") == "lead_bear"


def test_missing_price_history_does_not_fabricate_a_gate():
    """数据不足时 `_price_change_over` 返回 0.0 —— 那是「不知道」不是「没涨」。
    所以长窗口只用于**否决**，0.0 会放行；短窗口仍然要求明确反向。"""
    assert _lead(p60=0.0, p5=-3.0) == "lead_bull"
    assert _lead(p60=0.0, p5=-1.0) is None      # 短窗口不够明确就不报


def test_weak_resonance_still_blocked():
    assert _lead(p60=2.0, p5=-3.0, count=2) is None


# ── ② 内部人交易要说清多久以前 ──────────────────────────

def _insider(date_str):
    from scripts.insider_moves import describe_insider_activity
    return describe_insider_activity([{
        "holder_name": "轩景泉", "shares": 1000000, "ratio_total": 0.99,
        "ratio_own": 0, "avg_price": 10, "change_date": date_str,
        "reason": "二级市场买卖", "role": "董事长", "direction": "buy",
    }])


def _ago(days):
    from datetime import date, timedelta
    return (date.today() - timedelta(days=days)).isoformat()


def test_headline_says_how_long_ago():
    """妈妈得自己一条条看日期才发现是 4 月的 —— 标题就该说。"""
    r = _insider(_ago(118))
    assert "个月前" in r["headline"], r["headline"]
    assert r["days_since"] == 118


def test_recent_activity_shows_days_not_months():
    r = _insider(_ago(5))
    assert "5 天前" in r["headline"]
    assert not r["is_stale"]
    assert r["stale_note"] == ""


def test_stale_note_appears_and_reframes_it_as_history():
    """「自己人在买」和「自己人四个月前买过」是两回事，提示必须改变读法。"""
    r = _insider(_ago(118))
    assert r["is_stale"]
    note = r["stale_note"]
    assert "当历史看" in note and "不代表现在" in note
    assert "4 个月前" in note


def test_stale_threshold_is_about_a_quarter():
    """60 天≈一个季度，足够走完一轮行情 —— 奥来德那 4 个月里翻倍又腰斩。"""
    from scripts.insider_moves import STALE_DAYS
    assert STALE_DAYS == 60
    assert not _insider(_ago(59))["is_stale"]
    assert _insider(_ago(61))["is_stale"]


def test_stale_note_is_bilingual():
    from scripts.insider_moves import describe_insider_activity
    r = describe_insider_activity([{
        "holder_name": "X", "shares": 1000000, "ratio_total": 0.99, "ratio_own": 0,
        "avg_price": 10, "change_date": _ago(118), "reason": "二级市场买卖",
        "role": "董事长", "direction": "buy"}], locale="en")
    assert r["is_stale"]
    assert "history" in r["stale_note"].lower()
    assert not any("一" <= ch <= "鿿" for ch in r["stale_note"])


def test_no_data_is_safe():
    from scripts.insider_moves import describe_insider_activity
    r = describe_insider_activity([])
    assert r["stale_note"] == "" and r["days_since"] is None


# ── 展示层 ──────────────────────────────────────────────

def test_stale_note_renders_before_the_item_list():
    """列表按**重要性**排序、不按时间，所以时效必须在人开始读明细**之前**说清楚。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    assert 'insider-stale' in tpl
    assert tpl.index('insider.stale_note') < tpl.index('insider-list'), \
        "陈旧提示必须排在明细列表之前"
    css = open(os.path.join(ROOT, 'static', 'css', 'stock.css'), encoding='utf-8').read()
    assert '.insider-stale' in css
