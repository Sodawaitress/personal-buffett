"""US-142「谁在卖自己公司的股票」：惯例/机会性分类 + 双分母人话。

要点：Cohen-Malloy-Pomorski 证明只有机会性交易有信息量，股权激励行权那类机械交易
必须挑出去 —— 不区分会误报一堆，把用户对提示的信任耗光。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.insider_moves import (_own_pct, classify_insider_move,
                                   describe_insider_activity)


# ── 方向 ────────────────────────────────────────────────────────────────────

def test_negative_shares_is_sell():
    assert classify_insider_move(-5000, 0.01, 3, "竞价交易", "董事")["direction"] == "sell"

def test_positive_shares_is_buy():
    assert classify_insider_move(3000, 0.002, 6, "二级市场买卖", "高管")["direction"] == "buy"


# ── 惯例 vs 机会性 ──────────────────────────────────────────────────────────

def test_equity_incentive_small_is_routine():
    c = classify_insider_move(-1000, 0.001, 1.0, "股权激励行权", "高级管理人员")
    assert c["kind"] == "routine"

def test_lockup_expiry_small_is_routine():
    assert classify_insider_move(-2000, 0.002, 2.0, "解禁", "董事")["kind"] == "routine"

def test_big_sale_is_opportunistic_even_if_reason_mechanical():
    # 机械原因但卖掉本人持股一半 —— 卖多少仍是自己的选择
    c = classify_insider_move(-500000, 0.8, 50.0, "股权激励", "董事长")
    assert c["kind"] == "opportunistic"

def test_auction_trade_big_is_opportunistic():
    c = classify_insider_move(-800000, 0.6, 30.0, "竞价交易", "总经理")
    assert c["kind"] == "opportunistic"

def test_tiny_auction_trade_is_routine_noise():
    # 竞价交易但极小额 → 噪音，不该报
    c = classify_insider_move(-500, 0.0005, 0.2, "竞价交易", "董事")
    assert c["kind"] == "routine"

def test_key_person_gets_extra_weight():
    boss = classify_insider_move(-800000, 0.6, 30.0, "竞价交易", "董事长")
    staff = classify_insider_move(-800000, 0.6, 30.0, "竞价交易", "高级管理人员")
    assert boss["is_key_person"] and not staff["is_key_person"]
    assert boss["weight"] > staff["weight"]


# ── 占本人持股的分母：卖出要用「卖前持股」 ───────────────────────────────────

def test_own_pct_uses_pre_sale_base():
    # 卖 50 股，卖后剩 50 → 卖掉的是卖前(100)的 50%，不是卖后(50)的 100%
    assert _own_pct(-50, 50) == 50.0

def test_own_pct_buy_uses_end_hold():
    assert _own_pct(50, 150) == pytest_approx(33.33)

def pytest_approx(v, tol=0.05):
    class _A:
        def __eq__(self, other): return abs(other - v) <= tol
    return _A()

def test_own_pct_handles_zero_and_none():
    assert _own_pct(0, 0) is None
    assert _own_pct(None, None) is None


# ── 人话层 ──────────────────────────────────────────────────────────────────

def _move(**kw):
    base = {"holder_name": "张三", "role": "董事长", "shares": -800000,
            "ratio_total": 0.6, "ratio_own": 30.0, "reason": "竞价交易",
            "change_date": "2026-08-01"}
    base.update(kw)
    return base

def test_empty_returns_no_data():
    r = describe_insider_activity([])
    assert r["has_data"] is False
    assert "没有" in r["headline"]

def test_routine_only_is_not_reported_as_signal():
    r = describe_insider_activity([_move(reason="股权激励", ratio_own=1.0, ratio_total=0.001)])
    assert r["has_data"] is False
    assert r["routine_skipped"] == 1

def test_both_denominators_in_text():
    r = describe_insider_activity([_move()])
    assert r["has_data"]
    text = r["items"][0]["text"]
    assert "0.60%" in text and "30%" in text, text
    assert "总股本" in text and "持股" in text

def test_key_person_marked():
    r = describe_insider_activity([_move()])
    assert "核心决策人" in r["items"][0]["text"]

def test_caveat_present_when_reporting():
    r = describe_insider_activity([_move()])
    assert "私人" in r["caveat"] and "一笔不说明问题" in r["caveat"]

def test_net_direction():
    sells = [_move(holder_name="A"), _move(holder_name="B")]
    assert describe_insider_activity(sells)["net_direction"] == "sell"
    buys = [_move(holder_name="C", shares=800000), _move(holder_name="D", shares=900000)]
    assert describe_insider_activity(buys)["net_direction"] == "buy"


# ── 措辞纪律 + 双语 ─────────────────────────────────────────────────────────

def test_no_position_advice_and_no_bare_jargon():
    banned = ("仓位", "几成", "减仓", "清仓", "抄底", "建议买", "建议卖")
    r = describe_insider_activity([_move()])
    blob = r["headline"] + r["caveat"] + " ".join(i["text"] for i in r["items"])
    for w in banned:
        assert w not in blob, f"出现禁用词 {w}"

def test_english_has_no_chinese():
    han = re.compile(r'[一-鿿]')
    r = describe_insider_activity([_move(holder_name="Zhang")], locale="en")
    blob = r["headline"] + r["caveat"] + " ".join(i["text"] for i in r["items"])
    assert not han.search(blob), blob

def test_english_keeps_both_denominators():
    r = describe_insider_activity([_move(holder_name="Zhang")], locale="en")
    t = r["items"][0]["text"]
    assert "0.60%" in t and "30%" in t


# ── 真实案例回归：只看比例会漏掉大股东（US-142 冒烟测抓到的错分）────────────

def test_founder_block_trade_is_opportunistic_real_case():
    """002414 高德红外 黄立(创始人) 2026-02-25 一笔卖 1461.24 万股：
    占总股本 0.34%、但只占他本人持股 1.32%（持股基数极大）。
    纯比例阈值把它判成 routine —— 这恰恰是最该报的那种。"""
    c = classify_insider_move(
        shares=-14612400, ratio_total=0.3422, ratio_own=1.32,
        reason="大宗交易", position="董事", avg_price=13.5,
    )
    assert c["kind"] == "opportunistic", "创始人一笔卖两亿不能算机械交易"
    assert c["direction"] == "sell"

def test_block_trade_never_routine_even_when_small():
    # 大宗交易是刻意协商的通道，不存在「机械发生」
    c = classify_insider_move(-1000, 0.0001, 0.1, "大宗交易", "董事", avg_price=10)
    assert c["kind"] == "opportunistic"

def test_big_absolute_amount_triggers_even_with_tiny_ratios():
    c = classify_insider_move(-2000000, 0.01, 0.5, "竞价交易", "高级管理人员", avg_price=50)
    assert c["kind"] == "opportunistic", "1 亿的卖单不能因为比例小就忽略"

def test_small_amount_stays_routine():
    c = classify_insider_move(-500, 0.0005, 0.2, "竞价交易", "董事", avg_price=20)
    assert c["kind"] == "routine"

def test_amount_missing_falls_back_to_ratios():
    # 没有均价时不能崩，退回比例判定
    assert classify_insider_move(-14612400, 0.3422, 1.32, "竞价交易", "董事")["kind"] == "opportunistic"
    assert classify_insider_move(-500, 0.0005, 0.2, "竞价交易", "董事")["kind"] == "routine"


# ── 绝对金额：百分比会掩盖量级（黄立卖 1461 万股只占他持股 1%，读着像小事）──

def test_amount_shown_for_large_trades():
    from scripts.insider_moves import _fmt_amount
    assert _fmt_amount(-14612400, 13.5) == "2.0亿元"
    assert _fmt_amount(-2000000, 50) == "1.0亿元"

def test_amount_hidden_for_small_trades():
    from scripts.insider_moves import _fmt_amount
    assert _fmt_amount(-500, 20) == ""       # 1 万元，不值一提
    assert _fmt_amount(-15000, 20) == ""     # 30 万元

def test_amount_magnitude_correct_in_english():
    from scripts.insider_moves import _fmt_amount
    # 2 亿不能写成 2 million（曾经的 bug）
    assert _fmt_amount(-14612400, 13.5, "en") == "RMB 197 million"

def test_amount_missing_price_is_silent():
    from scripts.insider_moves import _fmt_amount
    assert _fmt_amount(-14612400, None) == ""

def test_amount_appears_in_item_text():
    r = describe_insider_activity([_move(shares=-14612400, avg_price=13.5, ratio_own=1.32)])
    assert "2.0亿元" in r["items"][0]["text"]

def test_english_uses_ascii_colon():
    r = describe_insider_activity([_move(holder_name="Zhang")], locale="en")
    assert "：" not in r["items"][0]["text"]


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
