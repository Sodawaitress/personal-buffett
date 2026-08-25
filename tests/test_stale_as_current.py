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
    assert "4 个月前" in note
    assert "失效" in note, "要说清作为入场信号已经失效"
    assert "基本面" in note, "但要保留它作为基本面证据的价值"


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
    note = r["stale_note"].lower()
    assert "expired" in note and "fundamental" in note
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


# ══ US-178：全库排查同一个病 + 按有效期分层 ══════════════

def _sig_src():
    return open(os.path.join(ROOT, 'radar_app', 'data', 'signal_events.py'),
                encoding='utf-8').read()


def test_labels_do_not_claim_more_time_than_the_data_has():
    """「持续」是时间跨度的断言，数据必须撑得住。

    · main_flow_in/out ← get_fund_flow 是 `ORDER BY date DESC LIMIT 1`，**一天**
    · inst_buying/selling ← stock_institute_hold_detail 的**单季度**快照，
      而且季报本身滞后约 2 个月
    """
    src = _sig_src()
    defs = src[src.index('_SIGNAL_DEFS = {'):src.index('RESONANCE_THRESHOLD')]
    assert '"主力持续流入"' not in defs and '"主力持续流出"' not in defs
    assert '"机构持续增持"' not in defs and '"机构持续减持"' not in defs
    assert '当日' in defs, "当日数据要在标签里说明"
    assert '最新季报' in defs, "季报数据要在标签里说明"


def test_fund_flow_really_is_one_day():
    """本测试的前提：改了取数窗口就来更新上面那条的措辞。"""
    src = open(os.path.join(ROOT, 'radar_app', 'data', 'stocks.py'), encoding='utf-8').read()
    seg = src[src.index('def get_fund_flow(code)'):][:400]
    assert 'ORDER BY date DESC LIMIT 1' in seg


def test_not_priced_claim_carries_the_news_age():
    """「市场还没反应，你早」说的是**事件当天**没异动，但 _early_warnings_for
    的窗口是 14 天 —— 13 天前的新闻会带着这句话出现在「今天有变化的」里，
    而推送里原本连日期都不显示。"""
    src = open(os.path.join(ROOT, 'scripts', 'stock_report.py'), encoding='utf-8').read()
    seg = src[src.index('for code, d in _early_warnings_for'):][:1400]
    assert '天前的消息' in seg, "隔天以上必须带上「几天前」"
    assert 'age <= 1' in seg, "只有当天/昨天才配说「还没反应」"


# ── cluster buy：文献认定最强的形态 ─────────────────────

def _ops(rows):
    from scripts.insider_moves import detect_cluster_buy
    return detect_cluster_buy(rows)


def test_cluster_buy_detected_on_the_real_case():
    """奥来德 688378 实例：3 人、5 笔、6 天、约 2.83% 股本 —— 教科书级。
    妈妈说「这个滞后的消息没有意义」，但按文献这恰恰是最强的一种，
    而且股价此后从约 24 涨到 62.89。错在呈现的尺度，不在数据。"""
    rows = [
        {"holder_name": "轩景泉", "direction": "buy", "ratio_total": 0.99, "change_date": "2026-04-30"},
        {"holder_name": "轩菱忆", "direction": "buy", "ratio_total": 0.68, "change_date": "2026-04-24"},
        {"holder_name": "MOON HYOUNG DON", "direction": "buy", "ratio_total": 0.30, "change_date": "2026-04-29"},
        {"holder_name": "轩景泉", "direction": "buy", "ratio_total": 0.70, "change_date": "2026-04-24"},
        {"holder_name": "轩菱忆", "direction": "buy", "ratio_total": 0.16, "change_date": "2026-04-30"},
    ]
    c = _ops(rows)
    assert c["n_insiders"] == 3
    assert c["n_tx"] == 5
    assert c["span_days"] <= 7
    assert abs(c["ratio_total"] - 2.83) < 0.01


def test_one_person_many_trades_is_not_a_cluster():
    """cluster 的关键是**多个不同的人**，不是多笔。同一个人分批买是一个决定。"""
    rows = [{"holder_name": "甲", "direction": "buy", "ratio_total": 0.5,
             "change_date": f"2026-04-{d}"} for d in (10, 12, 14, 16)]
    assert _ops(rows) == {}


def test_sells_do_not_form_a_cluster():
    """只看买入。卖出的理由可能很私人（买房、缴税），多人同时卖也可能只是
    解禁期到了 —— 买入没有这种「不得不」的理由。"""
    rows = [{"holder_name": n, "direction": "sell", "ratio_total": 0.5,
             "change_date": "2026-04-20"} for n in ("甲", "乙", "丙")]
    assert _ops(rows) == {}


def test_spread_out_buys_are_not_a_cluster():
    """窗口之外的分散买入不算 —— cluster 的信息量来自「同时」。"""
    rows = [{"holder_name": "甲", "direction": "buy", "ratio_total": 0.5, "change_date": "2026-01-10"},
            {"holder_name": "乙", "direction": "buy", "ratio_total": 0.5, "change_date": "2026-04-20"}]
    assert _ops(rows) == {}


# ── 有效期必须说出来 ────────────────────────────────────

def test_horizon_note_says_the_alpha_lands_early():
    """⚠️ 我第一版把这条写反了，值得留个记号。

    我原本写「这类信号的尺度是**月**，不是天：超额收益要在 6–12 个月里体现」——
    那是在劝人对一个**已经过期的信号**保持耐心，错在危险的方向。

    查准了（Wharton, 1975–1996 全样本）：
        约 **1/4** 的超额收益在头 **5 天**兑现
        约 **1/2** 在头 **1 个月**兑现
        而 Form 4 披露本身多数滞后 **21 天以上**
        近期研究更保守：21 个交易日后置信区间已包含 0

    **用户妈妈是对的**：4 个月前的买入，作为入场信号基本已经失效。
    12 个月 7.4% 那个数字是**累计总量**，不是「要等 12 个月才开始涨」。
    我把总量误读成了节奏。
    """
    from scripts.insider_moves import describe_insider_activity
    r = describe_insider_activity([{
        "holder_name": "甲", "shares": 1000000, "ratio_total": 0.99, "ratio_own": 0,
        "avg_price": 10, "change_date": _ago(30), "reason": "二级市场买卖", "role": "董事长"}])
    note = r["horizon_note"]
    assert "头一个月" in note, "必须说清大半 alpha 在头一个月内兑现"
    assert "基本面证据" in note, "正确用法是基本面证据，不是入场理由"
    assert "6–12 个月里体现" not in note, "这是被推翻的说法，不许回退"


def test_stale_note_does_not_ask_for_patience():
    """陈旧提示不能变成「再等等就好了」—— 那正是把总量误读成节奏的后果。"""
    r = _insider(_ago(118))
    note = r["stale_note"]
    assert "失效" in note
    assert "自己人当时有信心" in note, "要保留它作为基本面证据的价值"
    assert "再等" not in note


def test_card_shows_cluster_above_the_fold():
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    assert 'insider-cluster' in tpl and 'insider-horizon' in tpl
    assert tpl.index('insider.cluster_note') < tpl.index('insider-list'), \
        "最强的形态要排在明细之前"
    css = open(os.path.join(ROOT, 'static', 'css', 'stock.css'), encoding='utf-8').read()
    assert '.insider-cluster' in css and '.insider-horizon' in css


def test_no_data_still_has_every_field():
    from scripts.insider_moves import describe_insider_activity
    r = describe_insider_activity([])
    for k in ("cluster", "cluster_note", "horizon_note", "stale_note", "days_since"):
        assert k in r, f"缺字段 {k} —— 模板会 KeyError"
