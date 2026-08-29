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


def _tier(pe_pct=None, price_pct=None, one_off=False):
    return Q._value_tier(PROF, pe_pct, None, price_pct, "zh", one_off=one_off,
                         pe_current=16.5, pb_current=None, industry=None)


def test_price_position_alone_is_not_called_valuation():
    """只有股价位置时，不许说「估值便宜」。"""
    tier, rank, reason, basis = _tier(price_pct=20.0)
    assert basis == "price"
    phrase = Q._value_phrase(rank, True, basis, "zh")
    assert "估值便宜" not in phrase, f"股价位置被讲成了估值结论: {phrase}"
    assert "股价" in phrase and "判断不了" in phrase


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
