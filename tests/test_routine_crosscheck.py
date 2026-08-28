"""US-190：五选写作时强制查最新消息，和站上结论对刀。

## 用户的想法

> 「既然是你写的，写的时候就自动搜索检查最新信息、和网站结论对比，
>  既能反哺数据问题，又能提供每日 solid 的调查，是不是更好」

**这不是新发明，是把一次偶然变成流程。**

2026-08-25 查多邻国时，站上显示市盈率 **13.28 倍**，一搜 SEC 文件发现有
**2.567 亿一次性退税**，真实市盈率约 **43 倍** —— 一个影响全站估值评分、
而且朝着「让人买入」方向偏的 bug（US-172）。
**那次是随手查出来的，不是流程的一部分。**

## 为什么必须有守卫

五选由 Claude 在每日 routine 会话里写，不是代码生成的。所以这一步是
「靠自觉执行的流程」—— 而本仓所有沉默失败都证明靠自觉不成立
（US-150 双跑、US-158 静默失败、US-169 断链、US-174 被饿死…）。

守卫钉的是**文档契约**：Step 3.5 必须存在、必须排在写正文之前、
三类矛盾各自的处置必须写清、产出必须落两处。
文档一旦被改松，测试就红。

## 一条重要的边界

搜到的东西**不自动凌驾于数据**。传言和标题党进来只会污染判断，
所以只查「能证伪站上结论的事实」，且来源有优先级：
公司公告/交易所披露/监管文件 > 主流财经媒体 > 其它。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _routine():
    return open(os.path.join(ROOT, 'CLAUDE_ROUTINE.md'), encoding='utf-8').read()


def _step35():
    s = _routine()
    return s[s.index('### Step 3.5'):s.index('### Step 4')]


def test_crosscheck_step_exists():
    assert '### Step 3.5' in _routine()


def test_it_runs_after_picking_and_before_writing():
    """必须先有候选才知道搜什么；必须在写正文之前，否则改不了结论。"""
    s = _routine()
    assert s.index('### Step 3：') < s.index('### Step 3.5') < s.index('### Step 4：')


def test_three_discrepancy_types_each_have_an_action():
    """把矛盾分类不是为了好看 —— 三类的处置完全不同：
    滞后要按事实写、口径错误要**踢出五选**、事实反转要换股。
    不分类就会把「数据晚了一天」和「结论根本是错的」当成同一件事。"""
    seg = _step35()
    for kind in ('数据滞后', '口径错误', '事实反转'):
        assert kind in seg, f"缺少矛盾类型：{kind}"
    assert '不进五选' in seg, "口径错误的股票必须踢出五选，不能只是标注一下"


def test_output_goes_to_both_places():
    """推送给用户看（要正确结论），改进日志给开发看（要 bug 线索）。
    混在一起两边都用不好。"""
    seg = _step35()
    assert 'improvement_log' in seg
    assert '推送正文' in seg or '当天推送' in seg


def test_no_finding_must_still_be_recorded():
    """「今天没问题」和「今天没查」必须分得开 —— 否则这一步会悄悄消失，
    而且没人看得出来。这正是本仓所有沉默失败的形状。"""
    seg = _step35()
    assert '全部对得上' in seg or '没有矛盾也要写' in seg


def test_search_does_not_override_data_by_default():
    """传言和标题党进来只会污染判断。来源优先级必须写死在流程里。"""
    seg = _step35()
    assert '不自动凌驾' in seg or '不凌驾' in seg
    assert '公告' in seg and '传言' in seg


def test_it_excludes_opinions_and_price_targets():
    """只查能**证伪站上结论的事实**，不查「大 V 怎么看」「研报目标价」——
    那些是观点不是事实。"""
    seg = _step35()
    assert '观点不是事实' in seg or '观点' in seg
    assert '目标价' in seg


def test_scope_is_bounded_to_one_search_each():
    """深挖是专栏文章的活。每日 routine 不做深挖，否则会拖垮整个流程 ——
    routine 本来就常因为超时/门控而跳过（8 月 19 天里跳了 11 天）。"""
    seg = _step35()
    assert '最多搜一次' in seg or '不做深挖' in seg


def test_the_duolingo_precedent_is_recorded():
    """这一步的正当性来自一个真实战果。记下来，否则以后有人会觉得它是多余的
    仪式而删掉。"""
    seg = _step35()
    assert 'US-172' in seg
    assert '13.28' in seg and '43' in seg
