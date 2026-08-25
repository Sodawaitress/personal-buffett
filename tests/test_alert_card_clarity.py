"""US-176：让妈妈糊涂的那张卡 —— 金融概念的层次没理清。

## 她的原话（2026-08-25 微信）

> 他两个股票，一个是 **C 加**，但是他说他**看多预警**
> 另外一个…**华测检测是品级为 A**，但是这个又是**看空预警**

```
锐科激光  C+  →  看多预警      差评级 + 看多
华测检测  A   →  看空预警      好评级 + 看空
```

## 她不是看错了，是页面在自相矛盾

**评级和信号是两个不同系统的输出：**

| | 测什么 | 时间尺度 | 回答 |
|---|---|---|---|
| 评级 A/C+ | 基本面质量 | 年 | 这是不是一门好生意 |
| 看多/看空预警 | 资金流向 | 天 | 今天钱往哪走 |

两者同时成立**完全正常** —— 好公司天天有人卖。但页面并排放、都用红绿、
都用百分比，从不解释，就成了自相矛盾。

## 三层混淆，逐层拆

**① 同一个「99%」在三个地方意思完全不同**

    主力资金强度 99%   流出的**幅度**大 —— 方向藏在小字的正负号里
    机构调研活跃度 87%  最近有人来看 —— **无方向**
    接近触发 99%       离阈值只差一点 —— 中性，甚至是警告

百分比 + 进度条这个形式本身就在说「填满 = 好」。这三个没有一个是这意思。

**②「看多预警」这个词自相矛盾**

「预警」在中文里预示坏事。「警告你它要涨了」读不通。

**③ 徽章只反映一根条，却摆在卡片顶上像是整张卡的结论**

    const topDir = bars[0]?.direction    // 只取排第一那根

而条按「接近触发百分比」排序 —— 所以徽章实际等于「主力资金今天是流入还是流出」。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _idx():
    return open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read()


def _card():
    s = _idx()
    return s[s.index('function _renderApproachingCard'):s.index('// ── 股票搜索')]


def _css():
    return open(os.path.join(ROOT, 'static', 'css', 'watchlist.css'), encoding='utf-8').read()


# ── ① 无方向的量不许借红绿 ──────────────────────────────

def test_survey_and_participation_are_attention_not_bull():
    """US-167 把调研改成 attention，但只改了 _SIGNAL_DEFS ——
    `_calc_approaching` 有自己的一套，仍然写死 'bull'。
    于是 167 家（看空那只）和 1 家（看多那只）在页面上是同一种绿色。"""
    src = open(os.path.join(ROOT, 'radar_app', 'data', 'signal_events.py'),
               encoding='utf-8').read()
    body = src[src.index('def _calc_approaching'):src.index('def _price_5d')]
    for key in ('"key":       "survey"', '"key":       "participation"'):
        seg = body[body.index(key):]
        seg = seg[:seg.index('})')]
        assert '"direction": "attention"' in seg, f"{key} 仍在借用方向色"
    assert '"direction": "bull",' not in body, "_calc_approaching 里不该再有写死的 bull"


def test_attention_bar_has_a_neutral_color():
    css = _css()
    assert '.sr-appr-attention' in css, "attention 条需要中性色，否则会退回默认绿"
    seg = css[css.index('.sr-appr-attention'):][:120]
    for bullish in ('#81c784', '#e57373'):
        assert bullish not in seg, "关注度条不能用多空色"


# ── ② 徽章不能只看第一根条 ──────────────────────────────

def test_badge_uses_the_top_directional_bar_not_bars_zero():
    """bars[0] 可能是关注度条 —— 它没有方向可言，不能拿来定徽章。"""
    card = _card()
    assert 'bars[0]?.direction' not in card, "徽章不该直接取 bars[0] 的方向"
    assert 'dirBars' in card and "b.direction === 'bull'" in card


def _card_output_only():
    """只看会渲染出去的部分，剥掉注释 —— 注释里引用用户原话是应该保留的。"""
    return "\n".join(ln for ln in _card().splitlines()
                      if not ln.strip().startswith('//'))


def test_badge_wording_is_not_self_contradictory():
    """「看多预警」= 「警告你它要涨了」，读不通。改成说人话：钱在往哪走。"""
    out = _card_output_only()
    assert '看多预警' not in out and '看空预警' not in out
    assert '资金在流入' in out and '资金在流出' in out


def test_no_direction_bars_means_no_direction_claimed():
    """只有关注度信号时，绝不能默认成看多 —— 原来是 `|| 'bull'`。"""
    card = _card()
    assert "|| 'bull'" not in card
    assert '只有关注度信号' in card
    assert '.sr-appr-dir-none' in _css()


# ── ③ 分层：方向 vs 关注度 ──────────────────────────────

def test_bars_are_grouped_by_kind():
    """三根条原本平铺，看起来是同一类东西。它们不是。"""
    card = _card()
    assert '钱往哪走' in card
    assert '谁在关注' in card
    assert '不代表看涨' in card, "关注度分组要明说它不表示方向"
    assert '.sr-appr-group-label' in _css()


# ── 评级 vs 信号：妈妈问的那个矛盾 ──────────────────────

def test_section_explains_grade_versus_signal():
    """在**区块层面**说一次，不是每张卡都说 —— 每张卡都说会变成噪音。"""
    s = _idx()
    note = s[s.index('sr-appr-note'):][:600]
    assert '评级' in note
    assert '年' in note and '天' in note, "必须点明两者的时间尺度不同"
    assert '好公司也会被短期卖出' in note, "要直接消解那个「矛盾」"
    assert '.sr-appr-note' in _css()


def test_note_appears_once_not_per_card():
    s = _idx()
    assert s.count('sr-appr-note') <= 2, "说明只该出现一次（模板 + CSS 各一处）"
    assert 'sr-appr-note' not in _card(), "不该放进卡片里逐张重复"


# ── 柱状图：1 家不能画得和 167 家一样 ────────────────────

def test_survey_chart_labels_the_count():
    """柱高按**这只股票自己**的 6 个月最大值归一化，所以只有「1 家调研」的
    股票也会画出满格柱子。跨股票归一化在这个组件里做不到（没有全局尺度），
    所以把家数直接标出来 —— 让人一眼看见 1 和 167 的差别。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    assert 'svchart-n' in tpl
    assert re.search(r'svchart-n">\{\{ b\.count \}\}', tpl)
    css = open(os.path.join(ROOT, 'static', 'css', 'stock.css'), encoding='utf-8').read()
    assert '.svchart-n' in css


def test_survey_hint_says_how_many_institutions():
    """「最近一次调研 8 天前」没说是 1 家还是 167 家 —— 而那正是关键差别。"""
    src = open(os.path.join(ROOT, 'radar_app', 'data', 'signal_events.py'),
               encoding='utf-8').read()
    body = src[src.index('def _calc_approaching'):src.index('def _price_5d')]
    assert 'n_inst' in body and '家机构' in body
