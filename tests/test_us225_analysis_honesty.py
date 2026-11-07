"""US-225：一只新西兰亏损股的页面（AIR.NZ，2026-11-05 生产实测）。

A. 交易参数服从评级：评级减持的同一页，不能再说「当前即为买入机会」。
B. Groq 没写成信时，不再拼一个模板冒充信；下一轮 analyze-svc 重试。
C. 亏损公司的估值卡说「在亏损」，不说「数据不足」。
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

CJK = re.compile(r"[一-鿿]")
ENTRY_KEYS = ("entry_1_low", "entry_1_high", "entry_1_label",
              "entry_2_low", "entry_2_high", "entry_2_label")

# AIR.NZ 那天的形状：价格在 52 周区间 8% 处，没有均线 → 走 52 周分支的「极低位」
AIR_SIG = {"technicals": {}, "week_52_low": 0.37, "week_52_high": 0.62}
AIR_PRICE = {"price": 0.39}
# A 股形状：三条均线都有，价格在 MA60 和 MA250 之间 →「可分批介入」
CN_SIG = {"technicals": {"ma20": 10.0, "ma60": 9.5, "ma250": 11.0}}
CN_PRICE = {"price": 10.2}


def _tp(price, sig, market, locale, grade):
    import pipeline_analysis as pa
    return pa._compute_trading_params(price, sig, market=market, locale=locale, grade=grade)


# ── A ────────────────────────────────────────────────────

def test_weak_grade_drops_buy_zones_nz_and_cn():
    for price, sig, market in ((AIR_PRICE, AIR_SIG, "nz"), (CN_PRICE, CN_SIG, "cn")):
        for loc in ("zh", "en"):
            for grade in ("C", "C-", "D"):
                p = _tp(price, sig, market, loc, grade)
                for k in ENTRY_KEYS:
                    assert k not in p, (market, loc, grade, k)
                assert p.get("buy_suppressed") is True
                assert grade in p["position_label"]


def test_weak_grade_never_says_buying_opportunity():
    zh = _tp(AIR_PRICE, AIR_SIG, "nz", "zh", "C")
    en = _tp(AIR_PRICE, AIR_SIG, "nz", "en", "C")
    assert "买入机会" not in zh["position_label"]
    assert "buying opportunity" not in en["position_label"].lower()
    assert not CJK.search(en["position_label"])
    # 止损对已经持有的人仍然有用，保留
    assert zh.get("stop_loss_label") and en.get("stop_loss_label")


def test_strong_grades_unchanged():
    """C+ 及以上和以前完全一样（含不传 grade 的旧调用方）。"""
    for price, sig, market in ((AIR_PRICE, AIR_SIG, "nz"), (CN_PRICE, CN_SIG, "cn")):
        for loc in ("zh", "en"):
            base = _tp(price, sig, market, loc, None)
            for grade in ("A", "B+", "B", "B-", "C+"):
                assert _tp(price, sig, market, loc, grade) == base, (market, loc, grade)
            assert "entry_1_label" in base and "buy_suppressed" not in base


def test_template_hides_entry_rows_and_llm_buy_zones_when_suppressed():
    with open(os.path.join(ROOT, "templates/stock/letter.html"), encoding="utf-8") as f:
        html = f.read()
    assert "trading_params.buy_suppressed" in html
    assert "{% if trading_params.entry_1_label %}" in html
    assert "delete data['买入区间1']" in html


# ── B ────────────────────────────────────────────────────

def _fallback_result(monkeypatch, locale):
    import scripts.buffett_analyst as ba
    monkeypatch.setattr(ba, "_call_groq", lambda *a, **k: "")
    quant = {"score": 27, "grade": "C", "conclusion": "减持",
             "reasoning": "As turnaround: quality 27/100", "components": {}}
    tp = _tp(AIR_PRICE, AIR_SIG, "nz", locale, "C")
    return ba.analyze_stock_v3(
        code="AIR.NZ", name="Air New Zealand", market="nz",
        quant_result=quant, trading_params=tp, news=[], news_signals={},
        price={"price": 0.39}, fund_flow={}, locale=locale,
    )


def test_empty_groq_writes_no_fake_letter(monkeypatch):
    import scripts.buffett_analyst as ba
    for loc in ("zh", "en"):
        r = _fallback_result(monkeypatch, loc)
        assert r["letter_html"] == "", "模板不能冒充信"
        assert r["raw_output"] == ba.LETTER_FALLBACK_MARKER
        assert r["grade"] == "C"


def test_marker_matches_services_copy():
    import scripts.buffett_analyst as ba
    from radar_app.data import services
    assert services._LETTER_FALLBACK_MARKER == ba.LETTER_FALLBACK_MARKER


def _should(monkeypatch, last):
    from radar_app.data import services
    monkeypatch.setattr(services, "has_recent_material", lambda code: False)
    monkeypatch.setattr(services, "_last_analysis", lambda code: last)
    return services.should_analyze("AIR.NZ", rotation_days=3, held_codes=set())


def test_should_analyze_retries_missing_letter(monkeypatch):
    from datetime import date
    today = date.today().isoformat()
    assert _should(monkeypatch, (today, "（Layer 2 量化备用）")) == (True, "no_letter")
    # 量化刷新的行没有信、raw_output 为空 —— 不能因此每天都烧 LLM
    assert _should(monkeypatch, (today, None)) == (False, "cached")
    assert _should(monkeypatch, (today, "Dear friend, …")) == (False, "cached")
    assert _should(monkeypatch, (None, None)) == (True, "never")


def test_no_letter_has_a_priority():
    with open(os.path.join(ROOT, "scripts/svc_analyze.py"), encoding="utf-8") as f:
        assert '"no_letter": 2' in f.read()


def test_letter_only_job_clears_the_marker():
    with open(os.path.join(ROOT, "scripts/pipeline_jobs.py"), encoding="utf-8") as f:
        assert 'raw_output=result.get("raw_output")' in f.read()


# ── C ────────────────────────────────────────────────────

def _cheap(annual, locale, pe_pct=None):
    from scripts.buffett_signals import describe_cheapness
    return describe_cheapness(pe_pct, "down", [], locale=locale, annual=annual)


AIR_ANNUAL = [{"year": "2026", "net_profit": -2.42}, {"year": "2025", "net_profit": 1.05}]


def test_loss_making_tier_both_locales():
    zh = _cheap(AIR_ANNUAL, "zh")
    en = _cheap(AIR_ANNUAL, "en")
    assert zh["tier"] == en["tier"] == "loss_making"
    assert zh["headline"] == "在亏损，市盈率不适用"
    assert en["headline"] == "Losing money, so P/E doesn't apply"
    assert "转成了亏损" in " ".join(zh["reason"])
    for part in [en["headline"], en["actionable"], *en["reason"]]:
        assert not CJK.search(part), part
    assert "数据不足" not in zh["headline"]


def test_loss_direction():
    narrow = _cheap([{"year": "2025", "net_profit": -3}, {"year": "2026", "net_profit": -1}], "en")
    widen = _cheap([{"year": "2026", "net_profit": -5}, {"year": "2025", "net_profit": -1}], "en")
    assert "smaller" in " ".join(narrow["reason"])   # 年份顺序乱也要按年份排
    assert "bigger" in " ".join(widen["reason"])
    one_year = _cheap([{"year": "2026", "net_profit": -1}], "en")
    assert len(one_year["reason"]) == 1


def test_profitable_or_no_data_unchanged():
    assert _cheap([{"year": "2026", "net_profit": 5}], "en")["tier"] == "unknown"
    assert _cheap([], "en")["tier"] == "unknown"
    assert _cheap(None, "en")["tier"] == "unknown"
    # 有市盈率分位时不走亏损档（分位本身就说明能比）
    assert _cheap(AIR_ANNUAL, "en", pe_pct=10)["tier"] != "loss_making"


def test_loss_card_has_a_style():
    with open(os.path.join(ROOT, "static/css/stock.css"), encoding="utf-8") as f:
        assert ".cheap-loss_making" in f.read()
