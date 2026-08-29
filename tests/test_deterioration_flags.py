"""US-204：「便宜」和「便宜是有原因的」必须能被区分开。

生产上 LULU 拿到 **A 级买入**，依据是「ROE 31.8%（巴菲特线 15%）」+
市盈率处于近 3.5 年第 6 分位。两个数都是真的。

但它们描述的是**过去**。同期真实发生的是：

    营收增速   18.6% → 10.1% → 4.9%   （连续腰斩）
    毛利率     58.3% → 59.2% → 56.6%  （掉 2.6 个点）
    净利润     1,550 → 1,815 → 1,579  （绝对额下降）

9.4 倍市盈率配 4.9% 的增速，市场给的估值是对的，不是捡漏。

**ROE 描述过去，红旗要描述现在正在发生什么。**
"""
import pytest

from scripts.quantitative_rating import QuantitativeRater as Q

LULU = [{"year": "2026", "revenue": 11103, "net_profit": 1579, "gross_margin": 56.6},
        {"year": "2025", "revenue": 10588, "net_profit": 1815, "gross_margin": 59.2},
        {"year": "2024", "revenue": 9619,  "net_profit": 1550, "gross_margin": 58.3},
        {"year": "2023", "revenue": 8111,  "net_profit": 855,  "gross_margin": 55.4}]

DUOL = [{"year": "2025", "revenue": 10.38, "net_profit": 4.14, "gross_margin": 72.7},
        {"year": "2024", "revenue": 7.48,  "net_profit": 0.89, "gross_margin": 73.0},
        {"year": "2023", "revenue": 5.31,  "net_profit": 0.16, "gross_margin": 73.3},
        {"year": "2022", "revenue": 3.69,  "net_profit": -0.60, "gross_margin": 72.0}]


def test_lululemon_gets_all_three_flags():
    flags = Q._deterioration_flags(LULU)
    joined = " ".join(flags)
    assert "减速" in joined, flags
    assert "净利润在下滑" in joined, flags
    assert "毛利率" in joined, flags


def test_a_business_still_improving_gets_none():
    """反过来别乱插红旗：多邻国增速虽在放缓（44→41→39%），
    但没掉到复合增速的一半，利润和毛利率都在涨 —— 一条都不该有。"""
    assert Q._deterioration_flags(DUOL) == []


def test_flags_are_independent_and_skip_missing_fields():
    """缺字段就跳过那一条，不猜也不整段放弃。"""
    only_rev = [{"revenue": 100}, {"revenue": 200}, {"revenue": 210}]
    assert Q._deterioration_flags(only_rev) is not None   # 不抛异常
    only_net = [{"net_profit": 50}, {"net_profit": 100}]
    assert any("净利润" in f for f in Q._deterioration_flags(only_net))


def test_flags_reach_the_public_red_flag_list():
    """守接线：`extract_red_flags` 必须真的把它们带出去，
    否则算了也没人看见（US-202 那次 has_tax_windfall 就是接错了地方）。"""
    flags = Q.extract_red_flags(LULU, pe_pct=6, price_52week_pct=10.0,
                                news_signals={}, locale="zh")
    assert any("净利润在下滑" in f for f in flags), flags


def test_near_zero_base_cagr_is_not_a_perfect_score():
    """US-204 同一批：T1 Energy「营收 2年复合增速 **25067%**」→ 质量 100/100
    → A 级买入，顶在可投资清单第一位。

    和微利年的天价市盈率完全同形：分母接近零 → 数字爆炸 → 被当成特别好。
    从 0.4 亿涨到 100 亿说明的是「以前几乎没有生意」，不是「现在增长更强」。
    """
    tiny_base = [{"year": 2025, "revenue": 100.0},
                 {"year": 2024, "revenue": 4.0},
                 {"year": 2023, "revenue": 0.4}]
    score, why = Q._q_rev_cagr(tiny_base, {}, "zh")
    assert score < 100, f"极低基数拿了满分: {score} / {why}"
    assert "基数" in why, why


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_flags_never_mix_languages(locale):
    for f in Q._deterioration_flags(LULU, locale):
        has_cn = any("一" <= c <= "鿿" for c in f)
        assert has_cn == (locale != "en"), f
