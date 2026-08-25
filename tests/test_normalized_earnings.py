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


# ── 展示层：US-173 ──────────────────────────────────────

def _tpl(rel):
    return open(os.path.join(os.path.dirname(__file__), '..', rel),
                encoding='utf-8').read()


def test_card_shows_even_when_data_is_missing():
    """US-173：原来 `tier != 'unknown'` 才渲染，于是数据不足的股票
    （本地 13%，多为亏损股：市盈率为负算不出历史分位）**整张卡直接消失**，
    页面上什么都不说。

    用户 2026-08-25 原话：「安全边际卡到底在哪，我怎么怎么都没找到」。
    「我不知道」比「什么都不说」诚实，也不会让人以为功能坏了。
    """
    tpl = _tpl('templates/stock/letter.html')
    assert "cheapness.tier != 'unknown'" not in tpl, \
        "数据不足时不该整张卡消失"
    assert '{% if cheapness %}' in tpl


def test_unknown_tier_has_its_own_style():
    css = _tpl('static/css/stock.css')
    assert '.cheap-unknown' in css, "unknown 档要有自己的样式，否则没有左边框"


def test_adjusted_pe_appears_right_after_the_line_it_corrects():
    """修正句必须紧跟在「市盈率处在第 X 百分位」后面 —— 那句正是被它纠正的。
    隔开了就变成两条不相干的信息。"""
    from scripts.buffett_signals import describe_cheapness
    n = normalize(DUOL, "us")
    r = describe_cheapness(25, "up", ["公司在变强"], "zh", normalized=n, reported_pe=16.6)
    reasons = r["reason"]
    assert "百分位" in reasons[0]
    assert "一次性" in reasons[1], f"修正句应排第二，实际 {reasons}"
    assert r.get("adjusted_pe")


def test_unknown_tier_wording_stands_alone():
    """数据不足档前一句刚说「没有可比的历史估值」，再接「但这个市盈率…」读不通。"""
    from scripts.buffett_signals import describe_cheapness
    n = normalize(DUOL, "us")
    r = describe_cheapness(None, "up", [], "zh", normalized=n, reported_pe=16.6)
    assert r["tier"] == "unknown"
    joined = " ".join(r["reason"])
    assert "一次性" in joined
    assert not any(x.startswith("但") for x in r["reason"]), \
        f"数据不足档不该出现「但…」：{r['reason']}"


def test_warning_leads_with_the_one_off():
    """一次性收益会改变结论方向，比「下跌不代表跌完了」更要紧，要排在前面。"""
    from scripts.buffett_signals import describe_cheapness
    n = normalize(DUOL, "us")
    r = describe_cheapness(25, "up", [], "zh", normalized=n, reported_pe=16.6)
    assert r["warning"].startswith("利润里有一笔一次性的退税")


def test_clean_stock_card_is_untouched():
    """没有一次性收益的股票，这张卡必须和改动前一模一样。"""
    from scripts.buffett_signals import describe_cheapness
    a = describe_cheapness(25, "up", ["x"], "zh")
    b = describe_cheapness(25, "up", ["x"], "zh", normalized={}, reported_pe=16.6)
    assert a == b


def test_english_card_has_no_fullwidth_colon():
    """哥哥看英文版。模板里原来写死了中文全角「：」（US-148 同类欠债）。"""
    tpl = _tpl('templates/stock/letter.html')
    assert '{{ t.cheap_note_label }}：' not in tpl, "英文界面不该出现全角冒号"


def test_backfill_script_exists_and_is_additive():
    """新字段是后加的，旧记录都没有 —— 不补数这个功能就是完全不生效的。
    而且补数只能加字段，不能改写已有值（改写会让以后对不上账）。"""
    src = _tpl('scripts/backfill_tax_fields.py')
    assert 'pretax_income' in src and 'tax_provision' in src
    assert 'UPDATE stock_fundamentals SET annual_json' in src
    for banned in ('SET pe_current', 'DELETE FROM', 'DROP '):
        assert banned not in src, f"补数脚本不该做这个：{banned}"


# ── US-175：喂给评分系统，不只是展示 ────────────────────

def _rater():
    import scripts.quantitative_rating as q
    for _n, c in vars(q).items():
        if hasattr(c, "score_pe_valuation"):
            return c
    raise AssertionError("找不到评分类")


def test_one_off_cancels_the_cheap_score():
    """一次性收益抬高净利润 → 压低市盈率 → 压低历史分位 → 白拿「便宜」的分。
    这个分直接决定擂台排名和评级，所以不修的话，DUOL 这种股票会因为
    一笔退税排到前面去。"""
    R = _rater()
    for pct in (5, 10, 20, 30, 40):
        plain, _ = R.score_pe_valuation(pct, "zh")
        adj, desc = R.score_pe_valuation(pct, "zh", one_off=True)
        assert plain > 3, f"分位 {pct} 本应是便宜档"
        assert adj == 3, f"分位 {pct} 有一次性收益时应封顶到中性，实际 {adj}"
        assert "一次性" in desc


def test_one_off_does_not_invent_a_penalty():
    """只还原得出最近一年，算不出 5 年的还原分位 —— 真实分位**不知道**。
    不知道就不该给便宜分，但也不该硬罚成「贵」，那同样是编造。"""
    R = _rater()
    for pct in (50, 60):
        assert R.score_pe_valuation(pct, "zh", one_off=True)[0] == 3


def test_expensive_stays_expensive():
    """一次性收益只会让它更贵，不会让它变便宜 —— 已判贵的分数不能被抬高。"""
    R = _rater()
    for pct in (70, 80, 95, 100):
        plain, _ = R.score_pe_valuation(pct, "zh")
        adj, _ = R.score_pe_valuation(pct, "zh", one_off=True)
        assert adj == plain, f"分位 {pct}: {plain} → {adj}，贵的档不该动"


def test_clean_stock_scores_are_bit_identical():
    """没有一次性收益的股票，评分必须和改动前逐分相同。"""
    R = _rater()
    for pct in (None, 0, 10, 35, 55, 75, 99):
        assert R.score_pe_valuation(pct, "zh") == R.score_pe_valuation(pct, "zh", one_off=False)


def test_only_pe_is_affected():
    """PB 用净资产、价格位置用股价，都不受一次性**利润**影响。"""
    R = _rater()
    a, _ = R.score_valuation(10, 10, 5.0, "zh", one_off=False)
    b, _ = R.score_valuation(10, 10, 5.0, "zh", one_off=True)
    assert a - b == 4, f"只该 PE 少 4 分（7→3），实际总分差 {a - b}"


def test_scoring_reads_the_windfall_from_annual_data():
    """判据要接在真实数据上，不能是个永远为 False 的死参数。"""
    src = open(os.path.join(os.path.dirname(__file__), '..',
                            'scripts', 'quantitative_rating.py'), encoding='utf-8').read()
    assert 'has_tax_windfall' in src
    assert 'one_off=_one_off' in src


def test_one_off_message_is_bilingual():
    """哥哥看英文版（US-148 的债不再新增）。"""
    R = _rater()
    zh = R.score_pe_valuation(10, "zh", one_off=True)[1]
    en = R.score_pe_valuation(10, "en", one_off=True)[1]
    assert zh != en
    assert "one-off" in en.lower()
    assert not any("一" <= ch <= "鿿" for ch in en)
