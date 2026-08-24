"""US-166：已推荐股票的信号反转检测。

## 真实事故（2026-08-19 → 08-22）

8/19 五选把小商品城(600415) 写成「本轮 5 只中最干净的信号组合」，依据是
融券余量**大减 56.2%**（空头退场）+ 突破半年线 + 调研 0 家，
操作提示「未持仓可小仓位建仓 ¥12.30 附近」。

三天后融券变成 **+118.1%** —— 空头回来了而且翻倍。**中间没有任何一封信
提醒过。** 用户妈妈按建议加仓，当天被套。

## 根因四条
- RC1 五选是「选股」不是「持仓管理」：推荐完就断，Run 2 只验证显式「预言」
- RC2 ±80% 不是极端：实测 174 只里 28 只（16%）当天跨线
- RC3 判断规则缺「融券×调研」交叉表：最危险的那一格被写成「最干净」
- RC4 用户在券商买入不回流：status 仍是 watching、entry_price 为 null
      → **回访必须基于「推荐过」，不能基于「持仓」**
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.pick_reversal import TRACK_DAYS, detect_reversals, signals_of


def _stock(code="600415", name="小商品城", grade="A", conclusion="买入",
           short_pct=118.1, survey=0, price=12.48, meaningful=True):
    return {
        "code": code, "name": name,
        "analysis": {"grade": grade, "conclusion": conclusion, "quant_score": 65},
        "precursor": {
            "survey": {"count_30d": survey},
            "short_selling": {"change_pct": short_pct, "meaningful": meaningful},
        },
        "price": {"current": price},
    }


def _pick(short_pct=-56.2, grade="A", conclusion="买入", survey=0,
          date="2026-08-19", code="600415"):
    return {"code": code, "name": "小商品城", "date": date,
            "advice": "未持仓可小仓位建仓 ¥12.30 附近",
            "signals": {"grade": grade, "conclusion": conclusion,
                        "short_change_pct": short_pct,
                        "survey_count_30d": survey, "price": 12.30}}


# ── 核心回归：小商品城那一条必须被抓到 ────────────────────

def test_the_actual_incident_is_caught():
    r = detect_reversals([_pick()], [_stock()], today="2026-08-22")
    assert len(r) == 1
    assert r[0]["code"] == "600415"
    assert any("融券方向翻转" in x for x in r[0]["reasons"])
    assert r[0]["days_since"] == 3
    assert "12.30" in r[0]["picked_advice"]      # 当初说了什么要带出来


def test_no_reversal_when_signals_hold():
    """信号没变就不该报 —— 回访要精准，否则每天一堆噪音会被忽略。"""
    r = detect_reversals([_pick(short_pct=118.1)], [_stock(short_pct=118.1)],
                         today="2026-08-22")
    assert r == []


def test_same_day_not_reported():
    """推荐当天不算反转。"""
    assert detect_reversals([_pick()], [_stock()], today="2026-08-19") == []


def test_beyond_track_window_closed():
    """超过 21 天自然关闭 —— 再久的反转和当初那次推荐已经无关。"""
    assert detect_reversals([_pick(date="2026-07-01")], [_stock()],
                            today="2026-08-22") == []
    assert TRACK_DAYS == 21


# ── 融券方向翻转的边界 ──────────────────────────────────

def test_flat_transition_not_a_reversal():
    """从「无方向」变成有方向不算翻转 —— 那是信号出现，不是反转。"""
    r = detect_reversals([_pick(short_pct=5.0)], [_stock(short_pct=118.1)],
                         today="2026-08-22")
    assert not any("融券方向翻转" in x for x in (r[0]["reasons"] if r else []))


def test_tiny_base_does_not_trigger_reversal():
    """US-163：分母噪音不是信号。meaningful=false 时不判融券反转。"""
    r = detect_reversals([_pick(short_pct=-56.2)],
                         [_stock(short_pct=6700.0, meaningful=False)],
                         today="2026-08-22")
    assert not any("融券方向翻转" in x for x in (r[0]["reasons"] if r else []))


def test_reversal_the_other_way_also_caught():
    """空头建仓 → 空头撤退 同样是反转（当初因为看空而不推的，现在变了）。"""
    r = detect_reversals([_pick(short_pct=95.0)], [_stock(short_pct=-95.0)],
                         today="2026-08-22")
    assert any("融券方向翻转" in x for x in r[0]["reasons"])


# ── 其他三类反转 ────────────────────────────────────────

def test_grade_downgrade():
    r = detect_reversals([_pick(short_pct=118.1, grade="A")],
                         [_stock(short_pct=118.1, grade="B")], today="2026-08-22")
    assert any("评级下调" in x for x in r[0]["reasons"])


def test_grade_upgrade_not_a_reversal():
    r = detect_reversals([_pick(short_pct=118.1, grade="B")],
                         [_stock(short_pct=118.1, grade="A")], today="2026-08-22")
    assert r == []


def test_conclusion_turns_to_sell_side():
    r = detect_reversals([_pick(short_pct=118.1, conclusion="买入")],
                         [_stock(short_pct=118.1, conclusion="减持")],
                         today="2026-08-22")
    assert any("结论转向" in x for x in r[0]["reasons"])


def test_survey_dropping_to_zero():
    """当初的依据是「有机构在调研」，现在归零 —— 依据消失了。"""
    r = detect_reversals([_pick(short_pct=118.1, survey=3)],
                         [_stock(short_pct=118.1, survey=0)], today="2026-08-22")
    assert any("调研归零" in x for x in r[0]["reasons"])


def test_survey_zero_to_zero_is_not_a_reversal():
    """本来就是 0（64% 的 A 股都是），不该天天报。"""
    r = detect_reversals([_pick(short_pct=118.1, survey=0)],
                         [_stock(short_pct=118.1, survey=0)], today="2026-08-22")
    assert r == []


# ── 健壮性：坏数据不能让它挂 ──────────────────────────────

def test_missing_stock_in_snapshot_skipped():
    assert detect_reversals([_pick(code="999999")], [_stock()],
                            today="2026-08-22") == []


def test_garbage_pick_skipped():
    bad = [{}, {"code": "600415"}, {"date": "not-a-date", "code": "600415"}]
    assert detect_reversals(bad, [_stock()], today="2026-08-22") == []


def test_empty_inputs():
    assert detect_reversals([], [], today="2026-08-22") == []
    assert detect_reversals(None, None, today="2026-08-22") == []


# ── signals_of：台账存什么 ──────────────────────────────

def test_signals_of_extracts_exactly_what_reversal_needs():
    got = signals_of(_stock())
    assert set(got) == {"grade", "conclusion", "quant_score",
                        "short_change_pct", "survey_count_30d", "price"}
    assert got["short_change_pct"] == 118.1


def test_signals_of_tolerates_empty_stock():
    got = signals_of({})
    assert got["grade"] is None and got["price"] is None


# ── routine 文档必须带上这套规则 ──────────────────────────

def test_routine_mandates_the_followup_step():
    root = os.path.join(os.path.dirname(__file__), '..')
    doc = open(os.path.join(root, 'CLAUDE_ROUTINE.md')).read()
    assert 'pick_reversals' in doc, "Routine 必须读快照的 pick_reversals"
    assert 'picks_open.json' in doc, "Routine 必须写推荐台账，否则没有回访输入"
    assert doc.index('Step 2.5') < doc.index('Step 3：'), "回访必须在选股之前"


def test_routine_has_the_cross_table_and_relative_threshold():
    """RC3：融券×调研 交叉表；RC2：±80% 改成相对阈值。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    doc = open(os.path.join(root, 'CLAUDE_ROUTINE.md')).read()
    assert '最危险' in doc and '空头趁高位脱身' in doc, "缺融券×调研交叉表"
    assert '16%' in doc, "缺「±80% 不是极端」的实测证据"
    assert '前 5%' in doc, "缺相对阈值"
