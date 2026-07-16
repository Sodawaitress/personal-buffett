"""Tests for US-92 signal cross-product context functions."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from buffett_signals import (
    describe_margin_context,
    describe_survey_context,
    describe_participation_context,
    label_news_vs_institution,
    prophet_daily_score,
)


# ── describe_margin_context ──────────────────────────────────────────────────

def test_margin_neutral_returns_early():
    r = describe_margin_context(0, 0, 0, False, 0, 0)
    assert r["tier"] == "neutral"
    assert r["signal_strength"] == 0
    assert r["direction"] == "neutral"

def test_margin_heavy_short_price_up():
    r = describe_margin_context(60, 2.0, 0, False, 0, 0)
    assert r["tier"] == "heavy_short"
    assert r["direction"] == "mixed"
    assert r["signal_strength"] == 3
    assert "轧空" in r["price_context"] or "涨势" in r["price_context"]

def test_margin_heavy_short_price_down():
    r = describe_margin_context(60, -2.0, 0, False, 0, 0)
    assert r["tier"] == "heavy_short"
    assert r["direction"] == "bearish"
    assert r["signal_strength"] == 3

def test_margin_heavy_cover_price_up():
    r = describe_margin_context(-60, 2.0, 0, False, 0, 0)
    assert r["tier"] == "heavy_cover"
    assert r["direction"] == "bullish"
    assert r["signal_strength"] == 3

def test_margin_mild_cover_flat_price():
    r = describe_margin_context(-25, 0.3, 0, False, 0, 0)
    assert r["tier"] == "mild_cover"
    assert r["direction"] == "bullish"

def test_margin_participation_spike_adds_context():
    r = describe_margin_context(30, 2.0, 5, True, 0, 0)
    assert r["participation_context"] != ""
    assert "轧空" in r["participation_context"]

def test_margin_participation_spike_bearish():
    r = describe_margin_context(30, -2.0, 5, True, 0, 0)
    assert "出货" in r["participation_context"] or "联手" in r["participation_context"]

def test_margin_survey_adds_context():
    r = describe_margin_context(30, 0, 0, False, 3, 2.0)
    assert r["survey_context"] != ""
    assert "分歧" in r["survey_context"] or "调研" in r["survey_context"]

def test_margin_cover_with_survey():
    r = describe_margin_context(-30, 0, 0, False, 2, 1.0)
    assert "空头撤退" in r["survey_context"] or "调研" in r["survey_context"]

def test_margin_full_desc_contains_base():
    r = describe_margin_context(60, 1.5, 0, False, 0, 0)
    assert r["base_desc"] in r["full_desc"]


# ── describe_survey_context ──────────────────────────────────────────────────

def test_survey_none():
    r = describe_survey_context(0, 2.0, False, False, 0, 0)
    assert r["intensity"] == "none"
    assert r["signal_strength"] == 0
    assert r["direction"] == "neutral"

def test_survey_surge():
    r = describe_survey_context(6, 2.0, False, False, 0, 0)
    assert r["intensity"] == "surge"
    assert r["direction"] == "bullish"
    assert r["signal_strength"] == 3

def test_survey_elevated_with_foreign():
    r = describe_survey_context(3, 2.0, True, False, 0, 0)
    assert r["intensity"] == "elevated"
    assert any("外资" in m for m in r["modifiers"])

def test_survey_surge_repeat_institution():
    r = describe_survey_context(5, 2.0, False, True, 0, 0)
    assert any("多次" in m for m in r["modifiers"])

def test_survey_surge_with_margin_decrease():
    r = describe_survey_context(5, 2.0, False, False, -20, 0)
    assert any("撤退" in m or "双重" in m for m in r["modifiers"])

def test_survey_surge_with_margin_increase_causes_mixed():
    r = describe_survey_context(5, 2.0, False, False, 25, 0)
    assert r["direction"] == "mixed"
    assert any("分歧" in m for m in r["modifiers"])

def test_survey_declining():
    r = describe_survey_context(1, 5.0, False, False, 0, 0)
    assert r["intensity"] == "declining"
    assert r["direction"] == "bearish"

def test_survey_with_zero_avg_monthly():
    r = describe_survey_context(3, 0, False, False, 0, 0)
    assert r["intensity"] in ("surge", "elevated", "normal", "declining", "none")


# ── describe_participation_context ──────────────────────────────────────────

def test_participation_spike_price_up():
    r = describe_participation_context(50, 35, "上升", True, 2.0, 0)
    assert r["direction"] == "bullish"
    assert r["signal_strength"] == 3
    assert "买入" in r["full_desc"]

def test_participation_spike_price_down():
    r = describe_participation_context(50, 35, "上升", True, -2.0, 0)
    assert r["direction"] == "bearish"
    assert "出货" in r["full_desc"]

def test_participation_spike_flat_heavy_short():
    r = describe_participation_context(50, 35, "中性", True, 0, 20)
    assert r["direction"] == "mixed"
    assert "融券" in r["full_desc"]

def test_participation_rising_price_up():
    r = describe_participation_context(40, 34, "上升", False, 1.5, 0)
    assert r["direction"] == "bullish"
    assert "支撑" in r["full_desc"]

def test_participation_rising_price_down():
    r = describe_participation_context(40, 34, "上升", False, -1.5, 0)
    assert r["direction"] == "mixed"

def test_participation_declining():
    r = describe_participation_context(25, 35, "下降", False, 0, 0)
    assert r["direction"] == "bearish"
    assert "下滑" in r["full_desc"]

def test_participation_neutral():
    r = describe_participation_context(35, 35, "中性", False, 0, 0)
    assert r["direction"] == "neutral"
    assert r["signal_strength"] == 0


# ── label_news_vs_institution ────────────────────────────────────────────────

def test_label_positive_bullish():
    assert label_news_vs_institution("positive", "bullish") == "consistent"

def test_label_positive_bearish():
    assert label_news_vs_institution("positive", "bearish") == "divergent"

def test_label_negative_bullish():
    assert label_news_vs_institution("negative", "bullish") == "contrarian"

def test_label_negative_bearish():
    assert label_news_vs_institution("negative", "bearish") == "consistent"

def test_label_neutral_direction_returns_none():
    assert label_news_vs_institution("positive", "neutral") == "none"
    assert label_news_vs_institution("negative", "neutral") == "none"

def test_label_neutral_sentiment_returns_none():
    assert label_news_vs_institution("neutral", "bullish") == "none"

def test_label_missing_direction_returns_none():
    assert label_news_vs_institution("positive", "") == "none"
    assert label_news_vs_institution("positive", None) == "none"


# ── prophet_daily_score (US-75) ──────────────────────────────────────────────

def test_prophet_participation_above_avg_positive():
    r = prophet_daily_score({"latest": 30, "avg_30d": 22, "stdev": 4}, 0)
    assert r["value"] == 2.0  # z=2 clamped
    assert r["event_inst"] == 0

def test_prophet_participation_below_avg_negative():
    r = prophet_daily_score({"latest": 18, "avg_30d": 25, "stdev": 3.5}, 0)
    assert r["value"] < 0

def test_prophet_survey_bump_added():
    base = prophet_daily_score({"latest": 22, "avg_30d": 22, "stdev": 3}, 0)["value"]
    with_survey = prophet_daily_score({"latest": 22, "avg_30d": 22, "stdev": 3}, 5)["value"]
    assert with_survey > base
    assert with_survey == round(base + min(1.5, 0.3 * 5), 3)

def test_prophet_survey_bump_capped():
    r = prophet_daily_score({"latest": 22, "avg_30d": 22, "stdev": 3}, 100)
    assert r["value"] == 1.5  # bump capped at 1.5, z=0
    assert r["event_inst"] == 100

def test_prophet_empty_is_zero():
    r = prophet_daily_score({}, 0)
    assert r["value"] == 0.0
    assert r["spike"] is False

def test_prophet_missing_stdev_no_crash():
    r = prophet_daily_score({"latest": 30, "avg_30d": 22, "stdev": 0}, 0)
    assert r["value"] == 0.0  # sd=0 → no z contribution

def test_prophet_spike_flag_passthrough():
    r = prophet_daily_score({"latest": 22, "avg_30d": 22, "stdev": 3, "spike": True}, 0)
    assert r["spike"] is True


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✓  {name}")
                passed += 1
            except Exception as e:
                print(f"  ✗  {name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
