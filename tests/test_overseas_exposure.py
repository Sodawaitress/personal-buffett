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
    assert label(r["pct"]) == "主要做国内"


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
          "headline": "海外收入 83.5%",
          "meaning": "人民币每升值 1%，这 83.5% 的收入换回人民币就少约 1%。",
          "label": "大部分收入在海外"}
    html = env.from_string(seg).render(overseas=ov)
    assert "83.5" in html and "16.5" in html, "没同时显示海外和国内"
    assert "2025-12-31" in html, "没显示报告期"
    assert "−0.18" in html or "-0.18" in html, "没写明它不预测涨跌"
    assert "低估敞口比高估更危险" in html, "没说明未识别地区的处理方式"
