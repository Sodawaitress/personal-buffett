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


# ── US-191：先搞清楚 routine 跑在什么环境里 ──────────────

def test_routine_documents_its_execution_environment():
    """用户问：「你真的知道每日 routine 是咋搞的吗？整个链条，
    那不是个对话框哦」—— 我确实是假设出来的。

    从提交痕迹倒推：author == committer == `Claude <noreply@anthropic.com>`，
    每天 UTC 13:2x 固定，无 CI 痕迹。既不是 GitHub Actions
    （那会是 github-actions[bot]），也不是 Claude Code 会话
    （那会是仓库主人的身份）—— 是**第三个环境**：带 GitHub 连接的定时任务。

    **不知道环境就会设计出跑不动或者重复造轮子的步骤** ——
    2026-08-28 就发生过：给 routine 加 Step 3.5 时误以为要「新增」
    搜索能力，而 Gate ③ 早就在用 WebSearch 了。
    """
    s = _routine()
    assert '触发方式与运行环境' in s
    seg = s[s.index('## 触发方式与运行环境'):]
    assert 'noreply@anthropic.com' in seg, "要写明它以什么身份提交"
    assert 'github-actions' in seg, "要写明它**不是**什么（最容易认错的那个）"
    assert 'WebSearch' in seg, "要写明它有哪些能力"


def test_documented_trigger_time_discrepancy_is_not_hidden():
    """文档写 17:30 北京时间，实际提交是 UTC 13:2x ≈ 北京 21:2x —— 对不上。
    没查清楚之前不能假装一致，要把矛盾标出来。"""
    s = _routine()
    seg = s[s.index('## 触发时间'):]
    assert '对不上' in seg or '以实际观测为准' in seg


# ── US-191：搜索缓存陈旧 —— 有代价的教训 ────────────────

def test_step35_warns_about_stale_search_cache():
    """improvement_log 实测：08-19 搜天孚只拿到 08-17 的数据，
    搜美的只拿到 07-28 的。Gate ③ 为此迭代过方法论 ——
    「严守双站点同日报价会因缓存差异误报」。

    Step 3.5 第一版设计时假设「搜到的是最新的」，会把陈旧缓存
    误判成「事实反转」，制造大量假矛盾。
    """
    seg = _step35()
    assert '缓存' in seg and '陈旧' in seg
    assert '08-17' in seg or '07-28' in seg, "要留具体日期，抽象警告没人会当真"


def test_only_dated_facts_newer_than_snapshot_count():
    """判定规则必须是「找显著矛盾」而不是「找完全吻合」。"""
    seg = _step35()
    assert '搜不到东西 ≠ 有问题' in seg
    assert '晚于快照' in seg, "只有比快照更新的事实才能推翻快照"
    assert '无有效反证' in seg, "拿不准时要有一个明确的中性归类"


def test_false_positives_are_named_as_the_bigger_risk():
    """假矛盾比漏掉真矛盾更糟：它会把推送塞满噪音，用户不看了，
    真矛盾出现时反而被淹没。这个权衡要写在流程里，否则后来的人
    会以为「宁可错报不可漏报」。"""
    seg = _step35()
    assert '假矛盾比漏掉真矛盾更糟' in seg
