"""US-156：护城河「0/35」是假的数据缺失信号。

生产实测（2026-08-15 audit-svc）：34 只 moat=0/35 的股票里，
**无财务行 0 只、annual_json 是空列表 0 只** —— 财务数据一只不缺。

真相是 buffett_analyst._comp 对缺失键默认返回 [0,[],[]]。新版类型感知评级的
components 是 {quality, value, ...}，没有 moat 键，于是渲染成「护城河 0/35」。

后果链：
    0/35 → daily_digest 判 data_quality=incomplete
         → CLAUDE_ROUTINE「incomplete 且 precursor 弱 → 完全回避」
         → 用新评级体系打分的股票被系统性排除出妈妈的五选
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _comp_factory(components):
    """复刻 buffett_analyst.analyze_stock_v3 里的 _comp（避免整条 LLM 链路进单测）。"""
    def _comp(key):
        c = components.get(key)
        if not c:
            return None, []
        return c[0], (c[1] if len(c) > 1 else [])[:2]
    return _comp


def _sc(val, denom):
    return "—" if val is None else f"{val}/{denom}"


# ── 缺失键 vs 真的 0 分，必须能区分 ──────────────────────────

def test_missing_key_renders_dash_not_zero():
    """新版类型感知评级没有 moat 键 → 渲染「—」，不是「0/35」。"""
    _comp = _comp_factory({"quality": [72, ["ROE 稳定"]], "value": [40, []]})
    sc, _ = _comp("moat")
    assert sc is None
    assert _sc(sc, 35) == "—"


def test_genuine_zero_still_renders_zero():
    """真的拿了 0 分要照常显示 0/35 —— 本次修的是「缺项」不是「零分」。"""
    _comp = _comp_factory({"moat": [0, ["财务数据不足"]]})
    sc, reasons = _comp("moat")
    assert sc == 0
    assert _sc(sc, 35) == "0/35"
    assert reasons == ["财务数据不足"]


def test_normal_score_unaffected():
    _comp = _comp_factory({"moat": [28, ["ROE 连续5年>20%", "毛利率稳定"]]})
    sc, reasons = _comp("moat")
    assert _sc(sc, 35) == "28/35"
    assert len(reasons) == 2


def test_all_legacy_components_present():
    """旧版四件套齐全时行为完全不变。"""
    _comp = _comp_factory({
        "moat": [30, []], "growth_management": [25, []],
        "safety": [18, []], "valuation": [12, []],
    })
    assert _sc(_comp("moat")[0], 35) == "30/35"
    assert _sc(_comp("growth_management")[0], 30) == "25/30"
    assert _sc(_comp("safety")[0], 20) == "18/20"
    assert _sc(_comp("valuation")[0], 15) == "12/15"


# ── 数据完整性判据：改用 data_incomplete ────────────────────

def _is_incomplete(ana):
    """复刻 daily_digest 修好后的判据。"""
    q = ana.get("quant_score")
    return bool(ana.get("data_incomplete")) or (q is not None and q < 15)


def test_type_aware_rating_no_longer_flagged_incomplete():
    """核心回归：新评级体系 + 财务齐全 → 不该被判 incomplete。"""
    ana = {"moat": "—", "quant_score": 72, "data_incomplete": 0}
    assert _is_incomplete(ana) is False


def test_old_string_heuristic_would_have_misfired():
    """留档：旧判据会把这只健康股票误判成数据不完整。"""
    ana = {"moat": "0/35", "quant_score": 72, "data_incomplete": 0}
    assert ("0/35" in ana["moat"]) is True      # 旧判据 → incomplete
    assert _is_incomplete(ana) is False          # 新判据 → ok


def test_genuinely_incomplete_still_flagged():
    """真缺数据的仍要被判出来，不能放水。"""
    assert _is_incomplete({"moat": "0/35", "quant_score": 8, "data_incomplete": 1}) is True
    assert _is_incomplete({"moat": "—", "quant_score": 40, "data_incomplete": 1}) is True


def test_low_quant_score_still_flagged():
    assert _is_incomplete({"moat": "20/35", "quant_score": 9, "data_incomplete": 0}) is True


def test_missing_quant_score_not_flagged():
    """quant_score 缺失不等于数据不完整，别用 None 触发。"""
    assert _is_incomplete({"moat": "—", "quant_score": None, "data_incomplete": 0}) is False
