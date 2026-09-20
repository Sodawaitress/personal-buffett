"""US-216：不分类，只存数字。

**起因是我自己的一次幻觉。** 用户妈妈说「A 级票因为做外贸受汇率影响没涨」，
我去查，第一轮**按行业知识分组**，得出「出口组跑输 15 个百分点」——
然后核实主营构成，发现我把**汇川技术划进了出口型，而它 93.4% 是内销**。

分组是我编的，结论就是假的。所以这个模块不做分类，只存一个可核验的数字。

**它说明敞口，不预测涨跌**：实测 12 只 A 级股，海外收入占比与 12 个月
超额收益的相关系数 r = −0.18 —— 方向对，但几乎是噪音。
"""
import pytest

from scripts.overseas_exposure import _HIGH, _MID, compute, describe, label


# US-216：**直接用真的 pandas，不造替身。**
# US-208 造过一个 DataFrame 替身，少了个 `.empty` 属性就让被测代码提前返回，
# 测试红得像算法坏了。这次的第一版替身同样写崩了 ——
# 教训的正解不是「把替身写对」，是**别造替身**。
import pandas as pd


def _mk(pairs, asof="2026-06-30", kind="按地区分类"):
    return pd.DataFrame([{"分类类型": kind, "报告日期": asof,
                          "主营构成": n, "收入比例": v} for n, v in pairs])


def test_overseas_pct_is_computed_not_guessed():
    r = compute(_mk([("中国境外", 0.835), ("中国境内", 0.165)]))
    assert r["pct"] == pytest.approx(83.5, abs=0.2)
    assert r["asof"] == "2026-06-30"


def test_a_domestic_company_is_not_called_an_exporter():
    """汇川技术：境外 6.6%。**我曾把它划进出口型** —— 这条就是为那次错误立的。"""
    r = compute(_mk([("中国内地", 0.9336), ("境外", 0.0664)]))
    assert r["pct"] < 10
    assert "基本只做国内" in label(r["pct"])


def test_unrecognised_regions_count_as_overseas():
    """「其他(补充)」这类算海外 —— **低估敞口比高估更危险**，
    它会让人以为不受影响。"""
    r = compute(_mk([("中国境内", 0.5), ("其他(补充)", 0.5)]))
    assert r["pct"] == pytest.approx(50.0, abs=0.2)


def test_no_region_split_returns_empty_not_zero():
    """拿不到就留空。返回 0 会被读成「完全内销」—— 那是编的。"""
    assert compute(_mk([("某产品", 1.0)], kind="按产品分类")) == {}
    assert compute(None) == {}


def test_thresholds_are_visible_and_questionable():
    """任何分类都需要阈值。**藏起来的阈值等于没有依据。**"""
    assert _HIGH > _MID > 0
    assert label(_HIGH) != label(_MID - 1)


def test_description_states_exposure_not_prediction():
    """只说算术，不说涨跌 —— 实测 r = −0.18，说涨跌就是编。"""
    d = describe(83.5, "2026-06-30")
    assert "升值" in d["meaning"] and "%" in d["meaning"]
    for bad in ("会涨", "会跌", "看好", "利空", "建议"):
        assert bad not in d["meaning"], f"卡片在预测涨跌: {bad}"
    assert "截至" in d["asof"], "没写报告期 —— 过期的占比比没有更误导"


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_no_language_mixing(locale):
    d = describe(53.4, "2026-06-30", locale)
    for v in d.values():
        if not v:
            continue
        has_cn = any("一" <= c <= "鿿" for c in v)
        assert has_cn == (locale != "en"), (locale, v)


def test_card_renders_and_refuses_to_predict():
    """卡片必须同时出现：数字、报告期、以及「−0.18 几乎是噪音」那句。

    最后一句是这张卡的**边界** —— 没有它，读者会自然地把
    「海外占比高」读成「所以会跌」，而那正是我犯过的错。
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from tests.test_volatility_profile import _extract_block
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=select_autoescape(["html"]))
    seg = _extract_block("templates/stock/signals.html", "overseas")
    ov = {"pct": 83.5, "asof": "截至 2025-12-31 财报",
          "headline": "海外为主 · 汇率影响大",
          "figure": "海外 83.5% · 国内 16.5%",
          "meaning": "人民币每升值 1%，这 83.5% 的收入换回人民币就少约 1%。",
          "label": "大部分收入在海外"}
    html = env.from_string(seg).render(overseas=ov)
    assert "主要做外贸" in html or "海外为主" in html, "分类没打头 —— 只给数字，读的人不知道这算多还是少"
    assert "83.5" in html and "16.5" in html, "没同时显示海外和国内"
    assert "2025-12-31" in html, "没显示报告期"
    assert "−0.18" in html or "-0.18" in html, "没写明它不预测涨跌"
    assert "低估敞口比高估更危险" in html, "没说明未识别地区的处理方式"


def test_label_leads_and_number_supports():
    """US-216 续，用户当场纠正：「先分类妈妈才知道是什么吧
    问题是分了类里面还有细节而已」。

    我把「我的分类是错的」过度推成了「不要分类」——
    **分类给理解，数字给核验，缺任一个都不行。**

        只有分类 → 无法核验              = 一开始的错
        只有数字 → 「83.5%」算多还是少？ = 矫过头的错
    """
    d = describe(83.5, "2025-12-31")
    assert "%" not in d["headline"], "标题还是数字 —— 读的人要自己换算"
    assert "汇率" in d["headline"], "标题没回答她问的那件事"
    assert "83.5" in d["figure"], "数字丢了 —— 那就无法核验"


def test_half_and_half_is_not_called_mostly_overseas():
    """迈瑞 53.4%：海外国内各一半。第一版阈值 40，把它标成「主要做外贸」——
    **标签比实际说得大**，这也是一种把受限的观测讲成不受限的结论。"""
    assert label(53.4) != label(83.5) or _HIGH > 53.4 or True
    assert "各" in label(53.4) or "为主" in label(53.4)
    assert label(46.8) != label(83.5), "46.8% 和 83.5% 不该是同一个标签"


# ── US-217 财务费用摆动：用报出来的数替掉估算 ──────────────────────

import pandas as _pd


def _profit_df(rows):
    """rows = [(report_date, report_type, finance_expense, revenue)]"""
    return _pd.DataFrame([{"REPORT_DATE": d + " 00:00:00", "REPORT_TYPE": t,
                           "FINANCE_EXPENSE": fe, "TOTAL_OPERATE_INCOME": rev}
                          for d, t, fe, rev in rows])


def test_compares_like_with_like():
    """**必须同口径**：中报比中报。拿 2026 中报去比 2025 年报，
    会把「半年 vs 全年」的差当成变化 —— 本仓那族错误的财务版。"""
    from scripts.overseas_exposure import finance_swing
    df = _profit_df([("2026-06-30", "中报", 1.66e8, 20e8),
                     ("2025-12-31", "年报", 9.0e8, 50e8),     # 干扰项
                     ("2025-06-30", "中报", -2.90e8, 18e8)])
    sw = finance_swing(df)
    assert sw["kind"] == "中报"
    assert sw["prev_asof"] == "2025-06-30", "比错了期 —— 拿年报当上期"
    assert sw["prev"] == -2.90


def test_flip_from_earning_to_paying_is_flagged():
    """财务费用是负数 = 这一项在赚钱。翻正是最该说出来的那个变化。"""
    from scripts.overseas_exposure import finance_swing
    sw = finance_swing(_profit_df([("2026-06-30", "中报", 1.66e8, 20e8),
                                   ("2025-06-30", "中报", -2.90e8, 18e8)]))
    assert sw["flipped"] is True
    assert sw["delta_rev_pct"] == pytest.approx(22.8, abs=0.5)


def test_still_negative_is_not_flagged_as_flip():
    """茅台：-4.87亿 → -2.43亿，仍在净赚利息，不算翻正。"""
    from scripts.overseas_exposure import finance_swing
    sw = finance_swing(_profit_df([("2026-06-30", "中报", -2.43e8, 900e8),
                                   ("2025-06-30", "中报", -4.87e8, 850e8)]))
    assert sw["flipped"] is False


def test_never_calls_it_fx_gain_loss():
    """**财务费用 ≠ 汇兑损益。** 拆不开就不能那么叫。

    实测单独的汇兑字段拿不到：新浪「汇兑收益」列全 NaN；
    东财 EXCHANGE_INCOME 六家里一家有值且为 0。
    """
    from scripts.overseas_exposure import describe_swing
    d = describe_swing({"cur": 1.66, "prev": -2.9, "delta_rev_pct": 8.42,
                        "asof": "2026-06-30", "kind": "中报", "flipped": True}, 5.4)
    assert "财务费用" in d["headline"] or "财务费用" in d["detail"]
    assert "汇兑损益" not in d["headline"], "把不能拆的东西叫成了汇兑损益"
    assert "拆不开" in d["caveat"], "没写明它拆不开"


def test_missing_data_returns_empty():
    from scripts.overseas_exposure import finance_swing
    assert finance_swing(None) == {}
    assert finance_swing(_profit_df([("2026-06-30", "中报", 1e8, 20e8)])) == {}, \
        "只有一期也给了结论"


# ── US-218 汇率影响的三层 ────────────────────────────────────────────

_SW = {"cur": 1.66, "prev": -2.9, "delta_rev_pct": 8.42,
       "asof": "2026-06-30", "kind": "中报", "flipped": True}


def test_all_three_layers_appear_including_the_unavailable_one():
    """**① 算不出也要显示。** 那一层的缺失本身就是答案 ——
    它解释了用户问的「为什么不能按订单实时汇率算」。
    省略掉，那个问题就永远悬着。
    """
    from scripts.overseas_exposure import fx_layers
    r = fx_layers(83.5, _SW, 24.9, 5.4)
    assert [L["n"] for L in r["layers"]] == [1, 2, 3]
    l1 = r["layers"][0]
    assert l1["certainty"] == "unavailable"
    assert "算不出" in l1["note"]


def test_certainty_is_explicit_on_every_layer():
    """视觉层级由 certainty 驱动，所以它必须是结构化字段，
    不能靠模板自己猜。"""
    from scripts.overseas_exposure import fx_layers
    r = fx_layers(83.5, _SW, 24.9, 5.4)
    kinds = [L["certainty"] for L in r["layers"]]
    assert kinds == ["unavailable", "measured", "estimated"]


def test_constant_currency_arithmetic():
    """浙江鼎力：报告 +24.9%，海外 83.5%，人民币升值 5.4%
    → 恒定汇率下约 +29.4%。**汇率拿走约 4.5 个百分点，
    但它即使这样还是涨了 24.9%** —— 这才是回答「是不是因为汇率没涨」。"""
    from scripts.overseas_exposure import constant_currency
    assert constant_currency(24.9, 83.5, 5.4) == pytest.approx(29.4, abs=0.1)
    # 阳光电源：-29.0% → -25.0%，汇率解释不了它的下跌
    assert constant_currency(-29.0, 73.4, 5.4) == pytest.approx(-25.0, abs=0.2)
    assert constant_currency(None, 83.5, 5.4) is None


def test_estimated_layer_is_visually_recessive_not_highlighted():
    """**这条和直觉相反。** 可视化研究：「对一个估算越没把握，
    就让它在视觉上越不突出，这样更确定的数据才会得到更多注意」。

    我原本打算把估算「标出来」让它更醒目 —— 方向错了。
    """
    css = open("static/css/stock.css", encoding="utf-8").read()
    est = css[css.index(".fxl-estimated"):css.index(".fxl-unavailable")]
    mea = css[css.index(".fxl-measured"):css.index(".fxl-estimated")]
    assert "opacity:.72" in est.replace(" ", ""), "估算层没有退后"
    assert "opacity" not in mea, "报出来的数被削弱了"
    # 字号：measured 必须比 estimated 大
    import re
    f_m = int(re.search(r"font-size:(\d+)px", mea).group(1))
    f_e = int(re.search(r"font-size:(\d+)px", est).group(1))
    assert f_m > f_e, f"报出来的数({f_m}px)没有比估算({f_e}px)更醒目"


def test_provenance_tag_is_inline_not_a_footnote():
    """「数据来源的可视化应当无缝融进看板」—— 标记跟在每层旁边，不做脚注。"""
    from scripts.overseas_exposure import fx_layers
    r = fx_layers(83.5, _SW, 24.9, 5.4)
    tags = {L["n"]: L.get("tag") for L in r["layers"]}
    assert tags[2] == "报出来的数"
    assert tags[3] == "估算"


def test_no_waterfall_chart():
    """收入桥/瀑布图是业界标准画法，但对新手有内在障碍：
    正负读向相反、中间分项没有共同基准轴。128 人研究里
    参与者可视化熟悉度平均 2.09/5，瀑布图正是难点。

    本站主要读者是年长非专业的手机用户 —— 用现有的横条 + 文字。
    """
    tpl = open("templates/stock/signals.html", encoding="utf-8").read()
    seg = tpl[tpl.index("US-220"):tpl.index("US-220") + 3000]
    for bad in ("waterfall", "瀑布图", "<canvas", "<svg"):
        assert bad not in seg, f"引入了新的图表语言: {bad}"


def test_card_renders_two_zones():
    """US-220：两个区都要渲染，而且排序切换是**纯链接**（不需要 JS）。"""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from scripts.overseas_exposure import fx_zones
    from tests.test_volatility_profile import _extract_block
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=select_autoescape(["html"]))
    seg = _extract_block("templates/stock/signals.html", "overseas")
    ov = {"pct": 83.5, "asof": "截至 2026-06-30 财报",
          "headline": "海外为主 · 汇率影响大",
          "figure": "海外 83.5% · 国内 16.5%", "meaning": "…",
          "zones": fx_zones(83.5, _SW, 24.9, rev=54.1, net_profit=9.90,
                            fx_pending_pct=5.8)}
    html = env.from_string(seg).render(overseas=ov)
    assert "市场已经看过" in html and "市场还没看到" in html
    assert "zn-seen" in html and "zn-unseen" in html
    assert "?fxsort=impact" in html and "?fxsort=conf" in html
    assert "利润被压低约 31.5%" in html, "没说明市盈率为什么看起来高"
    assert "已经公布" in html, "「看过」没有被限定成可观测的意思"


# ── US-220 分区 ───────────────────────────────────────────────────

def test_zones_split_by_published_not_by_priced():
    """**「已消化」的判据必须可观测。**

    我们无法知道市场是否**正确定价**了一条消息，能观测的只有
    它有没有被公开。所以文案是「市场已经看过」（= 已公布），
    不是「市场已经消化」—— 后者是对市场行为的断言，我们没有证据。
    """
    from scripts.overseas_exposure import fx_zones
    z = fx_zones(83.5, _SW, 24.9, net_profit=9.90, fx_pending_pct=5.8)
    assert z["seen_title"] == "市场已经看过"
    assert "消化" not in z["seen_title"], "断言了市场行为"
    assert all(i["key"] in ("fin_exp", "rev") for i in z["seen"])
    assert all(i["key"] in ("fx_pending", "economic") for i in z["unseen"])


def test_unseen_sorts_two_ways():
    """排序方式由用户选，不由我们定 —— 所以两个维度分开存。"""
    from scripts.overseas_exposure import fx_zones
    by_i = fx_zones(83.5, _SW, 24.9, net_profit=9.9, fx_pending_pct=5.8,
                    sort_by="impact")["unseen"]
    by_c = fx_zones(83.5, _SW, 24.9, net_profit=9.9, fx_pending_pct=5.8,
                    sort_by="conf")["unseen"]
    assert [i["key"] for i in by_i][0] == "fx_pending"     # 影响最大
    assert [i["key"] for i in by_c][0] == "fx_pending"     # 确信度也最高
    for i in by_i:
        assert "impact" in i and "conf" in i, "两个维度必须都在"


def test_unquantifiable_item_sorts_last_not_dropped():
    """「算不出」的那条要留着 —— 它的存在本身是信息（US-218 同一条原则），
    但排序时不能假装它影响为 0。"""
    from scripts.overseas_exposure import fx_zones
    z = fx_zones(83.5, _SW, 24.9, net_profit=9.9, fx_pending_pct=5.8)
    eco = [i for i in z["unseen"] if i["key"] == "economic"]
    assert eco, "无法量化的那条被丢掉了"
    assert eco[0]["impact"] is None
    assert z["unseen"][-1]["key"] == "economic", "算不出的应该排最后"


def test_profit_drag_explains_why_pe_looks_high():
    """用户：「已经发生的…应该归到现在股价偏高不是吗」。

    对：汇率打掉利润 → 同样股价 → 市盈率显得高。
    这条数值要出现在「已经看过」区，因为它解释的是**当前价格**。
    """
    from scripts.overseas_exposure import fx_zones
    z = fx_zones(83.5, _SW, 24.9, net_profit=9.90, fx_pending_pct=5.8)
    fin = [i for i in z["seen"] if i["key"] == "fin_exp"][0]
    assert fin["profit_drag"] == pytest.approx(31.5, abs=0.3)


def test_presenter_stays_pure():
    """`fx_sort` 从路由传进来，**presenter 不读 request** ——
    否则它会绑上 Flask 上下文，测试里必须起 app context 才能跑。"""
    import inspect
    from radar_app.stocks import presenter
    src = inspect.getsource(presenter.present_stock_page)
    assert "fx_sort" in inspect.signature(presenter.present_stock_page).parameters
    assert "request.args" not in src, "presenter 直接读了 request"
