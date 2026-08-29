"""US-202：估值那句话必须对得起它手上的证据。

用户实拍多邻国页面：上方摘要写「估值便宜。好公司 + 便宜，难得」+ A 级买入，
下方卡片写「估值数据不足，判断不了贵还是便宜」。同一页，两句相反的话。

摊开之后是**三层叠在一起**：
1. 生产上 `pretax_income` 字段从没补过 → US-172/173/175 全空转
2. US-175 的一次性收益识别只写进了 `_rate_legacy`，而线上跑的是 `rate_stock`
3. 估值档不管靠什么证据得出，一律被叫做「估值X」——
   哪怕证据只是「股价比自己过去低」

第 3 条是这个仓库的老毛病：**把受限的观测讲成不受限的结论**
（US-151/163/176/182 同族）。股价位置只说得了「跌得深」，
说不了「便宜」——跌 80% 的股票，如果利润跌了 90%，反而更贵。
"""
import pytest
from scripts.quantitative_rating import QuantitativeRater as Q

PROF = {"v": "pe_or_price"}

# 多邻国 2022-2025 真实年报（亿美元）。2025 年所得税是 **负数** ——
# 那是把过去多年亏损积攒的抵税额一次性记进当年利润，
# 于是净利润(4.14) 反而**大于**税前利润(1.82)，经营上不可能。
DUOL_ANNUAL = [
    {"year": 2025, "revenue": 10.38, "pretax_income": 1.82,
     "tax_provision": -2.32, "net_margin": 39.9, "roe": 25.0, "net_profit": 4.14},
    {"year": 2024, "revenue": 7.48, "pretax_income": 1.02,
     "tax_provision": 0.14, "net_margin": 11.9, "roe": 7.0, "net_profit": 0.89},
    {"year": 2023, "revenue": 5.31, "pretax_income": 0.18,
     "tax_provision": 0.02, "net_margin": 3.0, "roe": 1.4, "net_profit": 0.16},
    {"year": 2022, "revenue": 3.69, "pretax_income": -0.59,
     "tax_provision": 0.01, "net_margin": -16.3, "roe": -6.0, "net_profit": -0.60},
]


def _tier(pe_pct=None, price_pct=None, one_off=False):
    return Q._value_tier(PROF, pe_pct, None, price_pct, "zh", one_off=one_off,
                         pe_current=16.5, pb_current=None, industry=None)


@pytest.mark.parametrize("metric,expect_basis", [
    ("pe_or_price", "price_fallback"),   # 有利润但缺分位 → 降级，等于不知道
    ("price",       "price"),            # 未盈利公司，设计上就只有这一根轴
])
def test_price_position_alone_is_not_called_valuation(metric, expect_basis):
    """只有股价位置时，不许说「估值便宜」—— 两种 price 都不许。"""
    tier, rank, reason, basis = Q._value_tier(
        {"v": metric}, None, None, 20.0, "zh",
        pe_current=16.5, pb_current=None, industry=None)
    assert basis == expect_basis
    phrase = Q._value_phrase(rank, basis == "price", basis, "zh")
    assert "估值便宜" not in phrase, f"股价位置被讲成了估值结论: {phrase}"
    assert "股价" in phrase


def test_percentile_evidence_says_where_it_came_from():
    """有自身历史分位时可以说估值，但要讲明是跟谁比的。"""
    tier, rank, reason, basis = _tier(pe_pct=15, price_pct=20.0)
    assert basis == "pct" and rank == 0
    assert Q._value_phrase(rank, True, basis, "zh") == "估值便宜（比自己历史）"


def test_one_off_gain_blocks_the_cheap_verdict():
    """利润里有一次性收益 → PE 被做低，这个「便宜」不算数。

    这是多邻国那条：账面 16.5x，扣掉一次性退税后真实约 43x。
    """
    tier, rank, reason, basis = _tier(pe_pct=15, price_pct=20.0, one_off=True)
    assert rank == 2, "有一次性收益还判便宜"
    assert tier != "便宜"
    assert "不算数" in reason


def test_one_off_reaches_the_live_path_not_just_legacy():
    """US-175 当初把 one_off 只接到了 `_rate_legacy`，
    线上跑的 `rate_stock` 一直没接 —— 于是它写了三个月的假「便宜」。

    守卫的是**接线**，不是算法：rate_stock 的源码里必须出现
    has_tax_windfall 并把它传给 _value_tier。
    """
    import inspect
    src = inspect.getsource(Q.rate_stock)
    assert "has_tax_windfall" in src, "rate_stock 没有识别一次性收益"
    assert "one_off=" in src, "识别了但没传给估值档"


def test_no_valuation_data_still_says_so():
    tier, rank, reason, basis = _tier()
    assert tier is None and basis is None
    assert Q._value_phrase(rank, False, basis, "zh") == "估值数据不足"


@pytest.mark.parametrize("basis", ["peer", "pct", "price"])
def test_english_phrasing_exists_for_every_basis(basis):
    """US-148 的双语债：小刚用英文版，别让他看到中文。"""
    out = Q._value_phrase(0, True, basis, "en")
    assert out and not any("一" <= c <= "鿿" for c in out), out


def test_degraded_price_basis_does_not_drive_the_grade():
    """US-202 第二轮：措辞改对了，**打分没改**。

    第一轮修完，摘要已经诚实地写「股价处于偏低位置（估值本身判断不了）」，
    但同一句话的尾巴还是「好公司 + 便宜，难得」+ A 级买入 ——
    因为评级矩阵仍然拿 rank=0 当「便宜」。

    **改了说法不等于改了判断。** 检查一个结论有没有真的修好，
    要看它下游的**每一个**消费者，不能只看最显眼的那句话。

    多邻国：股价在 52 周区间最底部 7.4%，profile 是 pe_or_price ——
    公司有利润，只是缺分位数据才降级到股价位置。这种「不知道」
    不许伪装成「便宜」。
    """
    out = Q.rate_stock(
        "DUOL", "多邻国", DUOL_ANNUAL,
        pe_percentile=None, pb_percentile=None,
        price_52week_pct=7.4,            # 52 周区间最底部
        news_signals={}, locale="zh", company_type="growth_tech",
        pe_current=16.5, pb_current=3.9, industry=None)
    # 先确认这条守卫**真的走到了估值那段** —— 第一版数据不全，rate_stock
    # 提前返回 NR，测试绿得毫无意义。空转的绿比红更危险（US-174 同一个坑）。
    assert out["grade"] != "NR", f"守卫空转了，没走到估值判断: {out['reasoning']}"
    assert "估值" in out["reasoning"] or "股价" in out["reasoning"]

    assert "便宜" not in out["reasoning"], f"估值不明还在说便宜: {out['reasoning']}"
    assert out["conclusion"] != "买入", f"估值不明还给买入: {out}"


def test_declared_price_metric_still_has_a_valuation_axis():
    """反过来别修过头：未盈利公司（profile v='price'）**本来就没有市盈率**，
    股价位置是设计上唯一的估值轴。把它也判成「无数据」等于废掉整个轴。

    区别在于：`price` 是声明的，`price_fallback` 是降级来的。
    """
    _t, _r, _why, basis = Q._value_tier(
        {"v": "price"}, None, None, 7.4, "zh",
        pe_current=None, pb_current=None, industry=None)
    assert basis == "price", "未盈利公司的估值轴被误伤了"
