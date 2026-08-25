"""US-172：把一次性收益从利润里剔掉，算真实市盈率。

## 事故

2026-08-25 用户问「多邻国值不值得买」，我们网站显示 **市盈率 13.28 倍** ——
便宜得不像话。而市场给的前瞻市盈率是 **48–53 倍**。差了近 4 倍。

原因在 `pipeline_fetch.py`：`"pe_current": info.get("trailingPE")`
—— 直接抄数据源的滚动市盈率，一次性收益原样吞进来。

DUOL 2025 年报：

    税前利润    $182.4M
    所得税      −$231.7M    ← 负数。不是交税，是退税
    净利润      $414.1M     ← **净利润 > 税前利润**

来源是递延所得税估值备抵释放，DUOL 在 10-Q 里明确披露全年一次性
税收收益 **$256.7M**。这是会计事件，不是生意变好。

**这个错的方向最危险**：它让贵的东西看起来便宜。系统里所有「估值便宜」
的判断（quantitative_rating 的 score_pe_valuation、lifecycle 的 pe 分位）
都会被它带偏，而且是**朝着让人买入的方向**带偏。

## 判据是结构性的，不是阈值猜测

正常情况下 净利润 = 税前利润 − 所得税，税是支出，所以净利润必然**小于**
税前利润。反过来只能是税项为负。不需要设任何阈值。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.normalized_earnings import (  # noqa: E402
    adjusted_pe, cashflow_divergence, describe, effective_tax_rate,
    has_tax_windfall, normalize)

# ── 真实数据：DUOL 2025 年报（亿美元），来自 yfinance / SEC 10-Q ──
DUOL = [
    {"year": "2025", "pretax_income": 1.824, "tax_provision": -2.317, "net_profit": 4.141},
    {"year": "2024", "pretax_income": 1.023, "tax_provision": 0.137,  "net_profit": 0.886},
    {"year": "2023", "pretax_income": 0.178, "tax_provision": 0.017,  "net_profit": 0.161},
]


# ── 判据 ────────────────────────────────────────────────

def test_net_above_pretax_is_a_windfall():
    assert has_tax_windfall(DUOL[0]) is True


def test_normal_years_are_not_flagged():
    """2024/2023 是正常年份 —— 误报会让这个功能很快被忽略。"""
    assert has_tax_windfall(DUOL[1]) is False
    assert has_tax_windfall(DUOL[2]) is False


def test_missing_or_bad_data_never_flags():
    """数据不全就说不知道，**绝不猜**。"""
    for row in ({}, {"net_profit": 4.1}, {"pretax_income": 1.8},
                {"pretax_income": None, "net_profit": 4.1},
                {"pretax_income": -1.0, "net_profit": 4.1},   # 税前亏损另说
                {"pretax_income": "x", "net_profit": "y"}):
        assert has_tax_windfall(row) is False, row


# ── 还原结果要对得上 SEC 披露 ───────────────────────────

def test_reconciles_with_sec_disclosure():
    """最重要的一条：独立算出的一次性收益，要和公司自己披露的对得上。

    SEC 10-Q 披露 2025 全年一次性税收收益 **$256.7M**（2.567 亿）。
    我们用「税前利润 × (1 − 历史有效税率)」反推，两条路径互不依赖。
    """
    n = normalize(DUOL, "us")
    assert n, "应识别出一次性收益"
    assert abs(n["one_off"] - 2.567) / 2.567 < 0.05, \
        f"算出 {n['one_off']}，披露 2.567，偏差超过 5%"


def test_normalized_profit_is_about_right():
    """账面 4.141 − 一次性 2.567 = 1.574。"""
    n = normalize(DUOL, "us")
    assert abs(n["normalized"] - 1.574) / 1.574 < 0.06


def test_adjusted_pe_lands_in_the_market_range():
    """账面 16.6 倍 → 还原后应落在市场给的前瞻 48–53 倍那个量级，
    而不是继续显示成十几倍。"""
    n = normalize(DUOL, "us")
    adj = adjusted_pe(16.6, n)
    assert adj is not None
    assert 35 <= adj <= 55, f"还原后 {adj} 倍，不在合理区间"
    assert adj > 16.6 * 2, "还原后必须显著高于账面 —— 这正是问题所在"


# ── 税率取自公司自己的历史 ──────────────────────────────

def test_uses_company_history_not_statutory_rate():
    """软件公司普遍有研发抵扣，实际税率长期低于法定 21%。
    用法定税率会低估真实利润，等于矫枉过正。"""
    n = normalize(DUOL, "us")
    assert n["rate_source"] == "公司历史有效税率"
    assert n["rate"] < 0.21, f"DUOL 历史有效税率应低于法定 21%，实际 {n['rate']}"


def test_windfall_year_is_excluded_from_the_rate_basis():
    """出事那年的税率是负的，绝不能拿来当基准 —— 否则会算出负税率，
    把真实利润推得比账面还高，方向完全反了。"""
    assert effective_tax_rate(DUOL[0]) is None
    assert effective_tax_rate(DUOL[1]) is not None


def test_falls_back_to_statutory_when_no_history():
    only = [DUOL[0]]
    n = normalize(only, "us")
    assert n and n["rate_source"] == "法定税率"
    assert n["rate"] == 0.21


def test_absurd_tax_rates_are_ignored():
    """有效税率 200% 或 1% 多半是数据错误，不能当基准。"""
    assert effective_tax_rate({"pretax_income": 1.0, "tax_provision": 2.0}) is None
    assert effective_tax_rate({"pretax_income": 1.0, "tax_provision": 0.01}) is None


# ── 没有一次性收益时必须闭嘴 ────────────────────────────

def test_clean_company_returns_nothing():
    clean = [{"year": "2025", "pretax_income": 2.0, "tax_provision": 0.5, "net_profit": 1.5}]
    assert normalize(clean, "us") == {}
    assert adjusted_pe(20.0, {}) is None
    assert describe({}, 20.0) == ""


def test_empty_input_is_safe():
    assert normalize([], "us") == {}
    assert normalize(None, "us") == {}


# ── A股兜底：现金流背离只是提示，不是判定 ────────────────

def test_cashflow_divergence_is_a_hint_not_a_verdict():
    d = cashflow_divergence({"net_profit": 4.0, "cfo": 1.0})
    assert d and "存疑" in d["hint"]
    # 措辞不能说死 —— 现金流背离也可能是应收/存货
    assert "一次性" not in d["hint"]


def test_healthy_cashflow_not_flagged():
    assert cashflow_divergence({"net_profit": 4.0, "cfo": 3.8}) == {}
    assert cashflow_divergence({"net_profit": 0, "cfo": 1.0}) == {}
    assert cashflow_divergence({}) == {}


# ── 给妈妈看的话 ────────────────────────────────────────

def test_explanation_avoids_jargon():
    """妈妈看的，不能出现「递延所得税估值备抵」这种词。"""
    txt = describe(normalize(DUOL, "us"), 16.6)
    assert "一次性" in txt and "退税" in txt
    for jargon in ("递延", "备抵", "估值备抵", "valuation allowance"):
        assert jargon not in txt, f"出现了行话：{jargon}"
    assert "42" in txt or "43" in txt, "要给出还原后的市盈率"


def test_english_explanation_exists():
    """US-148 的双语债：哥哥看英文版，别又只有中文。"""
    txt = describe(normalize(DUOL, "us"), 16.6, locale="en")
    assert txt and "one-off" in txt.lower()
    assert not any("一" <= ch <= "鿿" for ch in txt), "英文版混入了中文"


# ── 抓取端要真的把字段存下来 ────────────────────────────

def test_fetch_stores_pretax_and_tax_fields():
    """没有这两个字段，上面全部逻辑都是空转。"""
    src = open(os.path.join(os.path.dirname(__file__), '..',
                            'scripts', 'pipeline_fetch.py')).read()
    assert '_fin("Pretax Income"' in src
    assert '_fin("Tax Provision"' in src
    assert '"pretax_income":' in src and '"tax_provision":' in src
