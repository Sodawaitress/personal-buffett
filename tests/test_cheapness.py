"""US-141「便宜，而且不是因为公司变差」四态判定。

核心是不让「跌久了=便宜」这个错觉直接变成买入理由：低估值必须配上进化轴方向
才有意义，且低估值三态都要带挡刀句。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from buffett_signals import _FALLING_KNIFE, describe_cheapness


def test_cheap_and_improving_is_mispriced():
    r = describe_cheapness(12, "up", ["营收多年上行", "ROE上行"])
    assert r["tier"] == "mispriced"
    assert r["headline"] == "便宜，而且不是因为公司变差"
    assert any("12" in x for x in r["reason"])
    assert "营收多年上行" in r["reason"]

def test_cheap_and_deteriorating_is_value_trap():
    r = describe_cheapness(8, "down", ["净利多年下滑"])
    assert r["tier"] == "cheap_for_reason"
    assert r["headline"] == "便宜是有原因的"
    # 必须点出「不是市场错杀」，否则用户会当成机会
    assert any("变弱" in x for x in r["reason"])
    assert "越跌越买" in r["actionable"]

def test_cheap_and_flat():
    r = describe_cheapness(20, "flat")
    assert r["tier"] == "cheap_flat"

def test_rich_and_deteriorating_is_double_risk():
    r = describe_cheapness(95, "down")
    assert r["tier"] == "double_risk"
    assert r["headline"] == "贵，而且公司在变弱"

def test_rich_and_improving_is_good_but_pricey():
    r = describe_cheapness(85, "up")
    assert r["tier"] == "good_but_pricey"
    assert "贵不等于不能买" in r["actionable"]

def test_middle_is_neutral():
    r = describe_cheapness(50, "up")
    assert r["tier"] == "neutral"


# ── 挡刀句：低估值三态都必须有，高估值不需要 ────────────────────────────────

def test_falling_knife_warning_on_all_cheap_tiers():
    for evo in ("up", "down", "flat"):
        r = describe_cheapness(10, evo)
        assert r["warning"] == _FALLING_KNIFE, f"{evo} 缺挡刀句"

def test_no_warning_when_not_cheap():
    for p in (50, 85, 95):
        assert describe_cheapness(p, "up")["warning"] == ""


# ── 数据不足不硬猜（亏损公司 PE 为负，比不了）────────────────────────────────

def test_missing_percentile_returns_unknown():
    r = describe_cheapness(None, "up")
    assert r["tier"] == "unknown"
    assert "不足" in r["headline"]
    assert "市净率" in r["actionable"]

def test_boundary_values():
    assert describe_cheapness(30, "up")["tier"] == "mispriced"      # 30 含在便宜内
    assert describe_cheapness(31, "up")["tier"] == "neutral"
    assert describe_cheapness(70, "down")["tier"] == "double_risk"   # 70 含在贵内
    assert describe_cheapness(69, "down")["tier"] == "neutral"


# ── 措辞纪律：不许出现术语和仓位建议 ─────────────────────────────────────────

def test_no_jargon_and_no_position_advice():
    banned = ("安全边际", "满仓", "几成", "仓位", "加仓", "抄底")
    for p in (10, 50, 90, None):
        for evo in ("up", "flat", "down"):
            r = describe_cheapness(p, evo)
            text = r["headline"] + " ".join(r["reason"]) + r["warning"] + r["actionable"]
            for w in banned:
                assert w not in text, f"出现禁用词 {w}: {text}"


# ── 双语（Da-young 不懂中文，新功能不继承 zh-only 的债）────────────────────

def test_english_locale_has_no_chinese_in_own_strings():
    import re
    han = re.compile(r'[\u4e00-\u9fff]')
    for p in (10, 50, 90, None):
        for evo in ("up", "flat", "down"):
            r = describe_cheapness(p, evo, locale="en")   # 不传 evidence
            own = r["headline"] + " ".join(r["reason"]) + r["warning"] + r["actionable"]
            assert not han.search(own), f"en 输出里有中文: {own}"

def test_english_tiers_match_chinese_tiers():
    for p in (10, 20, 50, 85, 95, None):
        for evo in ("up", "flat", "down"):
            assert (describe_cheapness(p, evo, locale="en")["tier"]
                    == describe_cheapness(p, evo, locale="zh")["tier"])

def test_unknown_locale_falls_back_to_chinese():
    r = describe_cheapness(10, "up", locale="ko")
    assert r["headline"] == describe_cheapness(10, "up", locale="zh")["headline"]

def test_english_keeps_falling_knife_warning():
    r = describe_cheapness(10, "down", locale="en")
    assert r["warning"] and "further" in r["warning"]


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
    sys.exit(1 if failed else 0)
