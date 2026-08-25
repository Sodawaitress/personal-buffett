"""US-179：把「信息传导链」从一句说明文字，变成页面的骨架。

## 那句话早就写在页面上了

`i18n/stock.json`：

    研究 → 参与 → 资金 → 价格：调研和机构参与度动得最早，是最前面的领先信号

**这句话是对的，但我们只把它当说明，没把它当骨架。** 于是同一张卡上并排
摆着「以天计」和「以季计」的东西 —— 用户妈妈接连问出的五个问题，
全都是这个结构的必然产物：

    「华测检测是 A 级，为什么是看空预警？」   ← 比的是第 0 层和第 3 层
    「机构接连调研，股价却在跌」               ← 第 2 层且无方向
    「都长成这样了，他说股价还没反应」         ← 第 4 层早走完了
    「这个内部人士买入是 4 月，太滞后了」      ← 第 1 层，半衰期约 1 个月
    「一个 C+ 说看多，一个 A 说看空」          ← 两个系统的输出并排放

用户原话：「只要我们设计的层次合理，就能理解；层次混乱就理解不了。
有机结合是我们的方向。」

## 主轴为什么是「谁在说」

摊开全部信号后，三个维度在这一个轴上高度对齐：

    谁在说        独立于价格   兑现快慢   可信度
    公司自己人      是          月内       最高
    专业机构        是          季         高
    市场资金        半          天-周      中
    价格自己        否          —          背景

越靠近公司的人知道得越早、越独立于价格；越靠近价格的信号反应越快，
但它只是在复述已经发生的事（均线是价格算出来的，结构上不可能领先价格）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from radar_app.data.signal_layers import (  # noqa: E402
    LAYER_ORDER, LAYERS, SIGNAL_LAYER, cross_layer_conflict, group_by_layer,
    layer_directions, layer_of, transmission_state)

ROOT = os.path.join(os.path.dirname(__file__), '..')


# ── 链序就是模型，不能随手动 ────────────────────────────

def test_chain_order_matches_the_information_flow():
    """公司本身 → 自己人 → 机构 → 市场的钱 → 价格。
    这个顺序**同时**是「谁知道得早」「多快兑现」「有多可信」的顺序。"""
    assert LAYER_ORDER == ["company", "insider", "institution", "money", "price"]
    assert [L["order"] for L in LAYERS] == [0, 1, 2, 3, 4]


def test_price_layer_is_last_because_it_cannot_lead():
    """均线/VWAP 是**价格算出来的** —— 结构上不可能领先价格，只能复述。
    文献称内部人信号 exogenous to price action，而均线是 endogenous。"""
    price = [L for L in LAYERS if L["key"] == "price"][0]
    assert price["order"] == max(L["order"] for L in LAYERS)
    assert price["half_life"] is None, "派生量谈不上半衰期"
    assert "复述" in price["hint"]


def test_every_layer_states_its_scale():
    """层次混乱的一半原因就是没说清时间尺度。"""
    for L in LAYERS:
        assert L["scale"], f"{L['key']} 没说时间尺度"
        assert L["name"] and L["short"] and L["hint"]


def test_insider_half_life_matches_the_evidence():
    """Wharton 全样本：约 1/4 超额收益在头 5 天、约 1/2 在头 1 个月兑现。
    所以半衰期约 1 个月 —— 不是我一度写错的「6–12 个月」。"""
    ins = [L for L in LAYERS if L["key"] == "insider"][0]
    assert "1 个月" in ins["half_life"]


def test_institution_layer_is_marked_directionless():
    """调研是注意力不是方向（US-167）。层的元数据要带上这一点，
    否则下游又会默认它看多。"""
    inst = [L for L in LAYERS if L["key"] == "institution"][0]
    assert inst["directional"] is False


# ── 归层：不猜 ──────────────────────────────────────────

def test_known_signals_land_in_the_right_layer():
    assert layer_of("insider_cluster") == "insider"
    assert layer_of("survey_visit") == "institution"
    assert layer_of("main_flow_in") == "money"
    assert layer_of("ma250") == "price"


def test_unknown_signal_is_not_guessed_into_a_layer():
    """层的位置本身携带「多可信、多快兑现」的含义 ——
    塞错层比不显示更糟。"""
    assert layer_of("something_new") is None
    assert layer_of("") is None
    assert group_by_layer([{"key": "something_new"}])["money"] == []


def test_all_resonance_signals_are_assigned():
    """_SIGNAL_DEFS 里的每个信号都要有归属，否则分层视图会漏掉它。"""
    from radar_app.data.signal_events import _SIGNAL_DEFS
    for k in _SIGNAL_DEFS:
        assert k in SIGNAL_LAYER, f"{k} 没有归层"


# ── 传导到哪一层了 ──────────────────────────────────────

def test_upstream_only_is_the_real_lead_signal():
    g = group_by_layer([{"key": "insider_buy"}, {"key": "survey_visit"}])
    st = transmission_state(g)
    assert st["top"] == "insider"
    assert st["gap"] is True
    assert "还没跟上" in st["story"]


def test_downstream_only_is_not_a_lead_signal():
    """只有钱和价格在动 = 没有任何更懂的人在动，那不是领先。"""
    st = transmission_state(group_by_layer([{"key": "main_flow_out"}]))
    assert st["gap"] is False


def test_full_chain_says_it_has_transmitted():
    g = group_by_layer([{"key": "insider_buy"}, {"key": "main_flow_in"}])
    assert transmission_state(g)["gap"] is False
    assert "传导" in transmission_state(g)["story"]


def test_no_signals_is_safe():
    st = transmission_state({})
    assert st["reached"] == [] and st["top"] is None and st["story"] == ""


# ── 上下打架：两种方向含义相反 ──────────────────────────

def _conflict(sigs):
    return cross_layer_conflict(group_by_layer(sigs))


def test_insiders_selling_while_money_buys_is_the_dangerous_one():
    """最懂的人先走、接盘的还没反应过来 —— 这是最该小心的组合。
    原来的「多空分歧，暂看不清」把这个信息整个丢掉了。"""
    c = _conflict([{"key": "insider_sell", "direction": "bear"},
                   {"key": "main_flow_in", "direction": "bull"}])
    assert c["severity"] == "danger"
    assert "最懂的人先走" in c["text"]


def test_insiders_buying_while_money_leaves_is_only_a_watch():
    """方向反过来含义完全不同 —— 不危险，可能只是还没传导到。"""
    c = _conflict([{"key": "insider_buy", "direction": "bull"},
                   {"key": "main_flow_out", "direction": "bear"}])
    assert c["severity"] == "watch"
    assert "还没传导到" in c["text"]


def test_agreement_is_not_a_conflict():
    assert _conflict([{"key": "insider_buy", "direction": "bull"},
                      {"key": "main_flow_in", "direction": "bull"}]) == {}


def test_conflict_needs_both_an_upper_and_a_lower_layer():
    assert _conflict([{"key": "insider_buy", "direction": "bull"}]) == {}
    assert _conflict([{"key": "main_flow_in", "direction": "bull"}]) == {}


def test_attention_signals_do_not_create_a_direction():
    """调研是 attention —— 它不能让某一层显出方向来（US-167）。"""
    g = group_by_layer([{"key": "survey_visit", "direction": "attention"},
                        {"key": "main_flow_in", "direction": "bull"}])
    assert layer_directions(g)["institution"] is None
    assert cross_layer_conflict(g) == {}


# ── 这条链早就写在页面上了 ──────────────────────────────

def test_the_chain_sentence_still_exists_in_the_ui():
    """骨架和那句说明必须是同一个模型 —— 否则又变成两套。"""
    import json
    d = json.load(open(os.path.join(ROOT, 'i18n', 'stock.json'), encoding='utf-8'))
    hit = [v for v in d.values()
           if isinstance(v, dict) and "研究 → 参与 → 资金 → 价格" in str(v.get("zh", ""))]
    assert hit, "那句「研究→参与→资金→价格」不见了 —— 骨架从它来的"


# ── US-180：半衰期视觉化 ────────────────────────────────

def test_decay_is_exponential_and_hits_half_at_the_half_life():
    """定义就是这个：过一个半衰期，剩一半。"""
    from radar_app.data.signal_layers import remaining_strength
    assert abs(remaining_strength(30, 30) - 0.5) < 1e-6
    assert abs(remaining_strength(60, 30) - 0.25) < 1e-6
    assert abs(remaining_strength(0, 30) - 1.0) < 1e-6


def test_moms_case_reads_as_basically_expired():
    """4 月的内部人买入到 8 月 = 约 4 个半衰期 → 剩不到 10%。
    她说「这个滞后的消息没有意义」—— 数字支持她。"""
    from radar_app.data.signal_layers import decay_view
    v = decay_view(118, "insider")
    assert v["pct"] <= 10
    assert v["label"] == "基本失效"
    assert v["tone"] == "expired"


def test_fresh_signal_reads_as_fresh():
    from radar_app.data.signal_layers import decay_view
    v = decay_view(3, "insider")
    assert v["pct"] >= 90 and v["tone"] == "fresh"


def test_money_layer_decays_much_faster():
    """主力资金半衰期几天 —— 同样是 10 天前，钱的信号比内部人衰得多得多。"""
    from radar_app.data.signal_layers import decay_view
    assert decay_view(10, "money")["pct"] < decay_view(10, "insider")["pct"] / 2


def test_non_decaying_layers_return_nothing():
    """价格层是派生量、公司层是描述 —— 都谈不上半衰期，**不许硬算**。"""
    from radar_app.data.signal_layers import decay_view, remaining_strength
    assert decay_view(30, "price") == {}
    assert decay_view(30, "company") == {}
    assert remaining_strength(30, None) is None
    assert remaining_strength(None, 30) is None
    assert remaining_strength(30, 0) is None


def test_decay_text_avoids_the_jargon():
    """妈妈不需要先学会「半衰期」这个词才看得懂。"""
    from radar_app.data.signal_layers import decay_view
    t = decay_view(118, "insider")["text"]
    assert "半衰期" not in t
    assert "还剩约" in t and "效力减半" in t


def test_insider_card_carries_the_decay():
    from datetime import date, timedelta

    from scripts.insider_moves import describe_insider_activity
    d = (date.today() - timedelta(days=118)).isoformat()
    r = describe_insider_activity([{
        "holder_name": "甲", "shares": 1000000, "ratio_total": 0.99, "ratio_own": 0,
        "avg_price": 10, "change_date": d, "reason": "二级市场买卖", "role": "董事长"}])
    assert r["decay"]["pct"] <= 10
    assert describe_insider_activity([])["decay"] == {}


def test_stale_looks_stale_not_just_labelled():
    """实践共识：\"stale data should look stale\" —— 陈旧的要**看起来**陈旧。
    只挂文字标签不够，整块要跟着淡下去。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    assert 'decaybar' in tpl
    assert "'decay-' ~ insider.decay.tone" in tpl, "tone 要驱动整块的淡化"
    css = open(os.path.join(ROOT, 'static', 'css', 'stock.css'), encoding='utf-8').read()
    assert '.insider-card.decay-expired' in css and 'opacity' in css


def test_decay_never_relies_on_colour_alone():
    """金融界面通行原则：涨跌/强弱信号不能只靠颜色（色盲、灰度打印）。
    百分比数字和文字标签必须同时在。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    seg = tpl[tpl.index('class="decaybar'):][:700]
    assert 'decay.pct' in seg and 'decay.label' in seg


# ── US-180：页面骨架 ────────────────────────────────────

def test_chain_renders_on_the_signals_page():
    import db
    db.init_db()
    from app import app
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
    code = (db.get_user_holdings(1) or ['000793'])[0]
    h = c.get(f'/stock/{code}/signals').get_data(as_text=True)
    assert 'class="chain"' in h
    assert '信息传到哪了' in h
    for L in LAYERS:
        assert L['short'] in h, f"{L['short']} 没渲染出来"


def test_chain_never_shows_internal_keys():
    """页面上不该出现 company_quality 这种内部键名。"""
    import db
    db.init_db()
    from app import app
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
    code = (db.get_user_holdings(1) or ['000793'])[0]
    h = c.get(f'/stock/{code}/signals').get_data(as_text=True)
    seg = h[h.index('class="chain"'):h.index('chain-why')]
    for k in ('company_quality', 'main_flow_in', 'survey_visit'):
        assert k not in seg, f"内部键名 {k} 漏到页面上了"


def test_chain_explanation_is_collapsed_by_default():
    """渐进披露：默认只给摘要，想懂再展开（NN/g：可降认知负担约 55%）。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    # 块内有嵌套 {% if %}，不能拿第一个 {% endif %} 当结尾（我第一版就栽在这）
    seg = tpl[tpl.index('class="chain"'):tpl.index('US-119 层1')]
    assert '<details class="chain-why"' in seg
    head = seg[seg.index('<details class="chain-why"'):][:60]
    assert ' open' not in head, "解释默认应折叠，不能带 open 属性"


def test_directionless_layers_are_marked_in_the_ui():
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    assert 'chain-nodir' in tpl and '无方向' in tpl


def test_dangerous_conflict_is_visually_distinct():
    """上层看空+下层看多是最危险的组合，不能和 watch 长得一样。"""
    css = open(os.path.join(ROOT, 'static', 'css', 'stock.css'), encoding='utf-8').read()
    assert '.chain-danger' in css and '.chain-watch' in css
    assert css[css.index('.chain-danger'):css.index('.chain-danger') + 200] != \
           css[css.index('.chain-watch'):css.index('.chain-watch') + 200]
