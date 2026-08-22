"""US-164：融券知识卡片补两个情境（2026-08 癌症疫苗行情实证）。

原有 13 个情境覆盖不了这轮遇到的两种情况：

① **分母噪音** —— 泰晶科技(603738) 报「融券 +6700%」，是余量从接近零涨到一个
   小数字造成的假象。原来会落到「做空仓位大举增加」，把噪音当信号讲给用户。

② **消息出货** —— 沃森生物 +6.48%、30 日调研 0 次、融券 −29.7%。原来会落到
   `forced_cover`（空头认亏平仓），但那个说法暗示「有买盘在推」；真实情况是
   **没有任何机构来看过，买盘来自看标题的散户**，空头趁高位脱身。
   随后多家同概念公司连夜发澄清公告说没有实质业务。

情境顺序至关重要（第一个匹配的生效）：
- `base_too_small` 必须排第一 —— 它是数据有效性闸门，不是行为判断
- `news_driven_exit` 必须在 `forced_cover` 之前 —— 它多了「零调研」这个条件
- 但**真轧空**（参与度飙升）不能被它抢走
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from radar_app.knowledge.service import match_situation


def _m(**kw):
    kw.setdefault("meaningful", True)
    r = match_situation("short_selling", kw)
    return r["situation"] if r else None


def test_base_too_small_wins_over_everything():
    """泰晶科技实况：+6700% 但基数不到 1 万股。
    闸门必须排第一，否则会被「做空仓位大举增加」抢走。"""
    assert _m(change_pct=6700.0, meaningful=False) == "融券基数过小，本期无参考意义"


def test_base_gate_beats_even_strong_other_signals():
    """基数无效时，哪怕价格/调研条件齐全也不该给行为判断。"""
    got = _m(change_pct=-6700.0, price_change_pct=5.0,
             has_survey=True, pa_spike=True, meaningful=False)
    assert got == "融券基数过小，本期无参考意义"


def test_news_driven_exit_for_wosheng_case():
    """沃森生物实况：融券 −29.7%、当日 +6.48%、30 日调研 0 次。"""
    assert _m(change_pct=-29.7, price_change_pct=6.48,
              has_survey=False) == "消息拉升 · 空头趁高位脱身"


def test_real_squeeze_not_stolen_by_news_exit():
    """真轧空（参与度飙升 + 有调研）必须仍然判成轧空 ——
    「有机构在看」和「没人在看」是本质区别，不能混为一谈。"""
    assert _m(change_pct=-40.0, price_change_pct=2.0,
              pa_spike=True, has_survey=True) == "空头被迫离场（轧空尾声）"


def test_forced_cover_still_fires_when_survey_unknown():
    """没传 has_survey 时不该误判成消息出货（条件缺失即不匹配）。"""
    assert _m(change_pct=-40.0, price_change_pct=2.0) == "空头认亏平仓（被迫的）"


def test_divergence_for_beigene_case():
    """百济神州实况：融券 +67.8% + 有机构调研 = 机构内部分歧。"""
    assert _m(change_pct=67.8, price_change_pct=-3.22,
              has_survey=True) == "机构内部有分歧"


def test_bottom_signal_for_hikvision_case():
    """海康威视实况：融券 −85.8%（跨过 routine 的 ±80% 线）+ 有调研。"""
    assert _m(change_pct=-85.8, price_change_pct=0.97,
              has_survey=True) == "底部信号：空头撤 + 机构在调研"


def test_gate_is_first_situation_in_file():
    """顺序是行为的一部分 —— 用文件顺序断言，防止有人重排。"""
    import yaml
    root = os.path.join(os.path.dirname(__file__), '..')
    with open(os.path.join(root, 'knowledge/short_selling.yaml')) as f:
        spec = yaml.safe_load(f)
    ids = [s["id"] for s in spec["situations"]]
    assert ids[0] == "base_too_small"
    assert ids.index("news_driven_exit") < ids.index("forced_cover")


def test_meaningful_and_has_survey_are_coerced_as_bool():
    """API 层要把这两个字段当布尔解析，否则 '?meaningful=false' 会变成真值字符串。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    src = open(os.path.join(root, 'radar_app/knowledge/routes.py')).read()
    i = src.index('_BOOL_FIELDS')
    block = src[i:i + 200]
    assert 'meaningful' in block
    assert 'has_survey' in block
