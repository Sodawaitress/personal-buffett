"""US-150：事件驱动链的结构守卫。

原来 6 个服务各自排 cron，链条横跨 07:32→15:06 UTC 共 7.5 小时，其中约
1.5 小时纯空转（串行总耗时其实只有 244 分钟）。后果是 snapshot 在
CST 23:06 才生成，而 Claude Routine 21:30 就去读了 —— 妈妈的信永远基于
前一天收盘，周一更是读到周五的（72h，US-149 的 26h 宽通道也兜不住）。

这些断言守的是**结构**，不是时间：任何人把链拆断、把 cron 加回来造成双跑、
或者漏掉失败传播守卫，测试都会红。
"""
import os

import yaml

ROOT = os.path.join(os.path.dirname(__file__), '..')
WF = os.path.join(ROOT, '.github', 'workflows')


def _load(name):
    with open(os.path.join(WF, name)) as f:
        d = yaml.safe_load(f)
    # PyYAML 把裸 `on:` 解析成布尔 True
    return d, (d.get(True) or d.get('on') or {})


# 链序：fetch → analyze → push → radar ──桥接──> market → Daily Cron → digest
#
# ⚠️ GitHub 硬限制：workflow_run 最多串三层。
#   "You can't use workflow_run to chain together more than three levels of
#    workflows ... workflows E and F will not be run."
# 08-21 实测：fetch→analyze(1)→push(2)→radar(3) 全部正常，market(4) 及之后
# 三个服务**全没触发**（靠 watchdog 补跑 digest 才没断供）。
#
# 所以链条被切成两段，中间用 radar 末尾的 `gh workflow run` 桥接 ——
# workflow_dispatch 会重置嵌套计数。
SEG1 = [
    ('fetch-svc.yml',   None),                    # cron 锚点
    ('analyze-svc.yml', 'fetch-svc (US-121)'),    # 第 1 层
    ('push-svc.yml',    'analyze-svc (US-121)'),  # 第 2 层
    ('radar-svc.yml',   'push-svc (US-121)'),     # 第 3 层 ← 上限
]
SEG2 = [
    ('market-svc.yml',  None),                    # 由 radar 桥接 dispatch
    ('cron.yml',        'market-svc (US-138)'),   # 第 1 层
    ('digest-svc.yml',  'Daily Cron'),            # 第 2 层
]
CHAIN = SEG1 + SEG2

MAX_WORKFLOW_RUN_DEPTH = 3


def test_chain_is_wired_in_order():
    for fname, upstream in CHAIN:
        _, on = _load(fname)
        if upstream is None:
            continue
        wr = on.get('workflow_run')
        assert wr, f"{fname} 应该由 workflow_run 触发"
        assert wr['workflows'] == [upstream], \
            f"{fname} 的上游应是 {upstream}，实际 {wr['workflows']}"


def test_no_segment_exceeds_github_nesting_limit():
    """回归 08-21 的静默断链：任何一段的 workflow_run 深度都不能超过 3。

    这是 GitHub 的硬限制，超了不报错、不告警，**下游就是不跑**。
    第一版测试只查「链序对不对」，所以没抓到 —— 引用全都是对的，
    只是第 4 层永远不会被触发。
    """
    for seg_name, seg in (("SEG1", SEG1), ("SEG2", SEG2)):
        depth = sum(1 for _, up in seg if up is not None)
        assert depth <= MAX_WORKFLOW_RUN_DEPTH, (
            f"{seg_name} 的 workflow_run 深度 {depth} 超过 GitHub 上限 "
            f"{MAX_WORKFLOW_RUN_DEPTH} —— 第 {MAX_WORKFLOW_RUN_DEPTH+1} 层起会静默不跑"
        )


def test_bridge_exists_between_segments():
    """两段之间必须有显式桥接，否则 SEG2 永远不会启动。"""
    body = open(os.path.join(WF, 'radar-svc.yml')).read()
    assert 'gh workflow run market-svc.yml' in body, \
        "radar-svc 末尾必须 dispatch market-svc（跨段桥接）"
    assert 'if: always()' in body, "桥接要 always()，radar 挂了也放行下游"
    d, _ = _load('radar-svc.yml')
    perms = d['jobs']['radar'].get('permissions') or {}
    assert perms.get('actions') == 'write', "桥接需要 actions: write 权限"


def test_segment2_entry_is_dispatch_only():
    """market-svc 必须靠 dispatch 进来。改回 workflow_run 会再次静默断链。"""
    _, on = _load('market-svc.yml')
    assert 'workflow_dispatch' in on
    assert 'workflow_run' not in on, \
        "market-svc 不能用 workflow_run —— 它在链上是第 4 层，会静默不跑"


def test_only_fetch_has_a_cron_anchor():
    """多一个 cron 就多一条并行链 —— push-svc 若被 cron 触发会**重复推送给妈妈**。"""
    for fname, _upstream in CHAIN:
        _, on = _load(fname)
        has_cron = 'schedule' in on
        if fname == 'fetch-svc.yml':
            assert has_cron, "fetch-svc 是唯一的 cron 锚点（A股收盘后）"
        else:
            assert not has_cron, f"{fname} 不该有 cron —— 会和链式触发形成双跑"


def test_upstream_names_match_actual_workflow_names():
    """workflow_run 按 name 匹配。改了 name 却忘了改引用 = 链条静默断裂。"""
    names = {}
    for fname, _ in CHAIN:
        d, _on = _load(fname)
        names[fname] = d['name']
    for fname, upstream in CHAIN:
        if upstream is None:
            continue
        assert upstream in names.values(), \
            f"{fname} 引用的上游 '{upstream}' 不存在于任何 workflow 的 name"


def test_failure_propagates_only_cancelled_blocked():
    """上游 failure 仍要放行下游 —— 各服务本就设计成互相独立。
    只有 cancelled 才挡（那通常是超时或人工中止）。"""
    for fname, upstream in CHAIN:
        if upstream is None:
            continue
        d, _ = _load(fname)
        conds = [str(j.get('if') or '') for j in d['jobs'].values()]
        joined = ' '.join(conds)
        assert "conclusion != 'cancelled'" in joined, f"{fname} 缺失败传播守卫"
        assert "conclusion == 'success'" not in joined, \
            f"{fname} 不该只认 success —— 会让一环失败导致全天归零"


def test_watchdog_exists_and_checks_artifact_not_task():
    """看门狗查的必须是「产物在不在」，不是「任务跑没跑」——
    这个仓库所有的沉默失败都是「跑了、没报错、但没产出」。"""
    d, on = _load('watchdog-svc.yml')
    assert 'schedule' in on, "watchdog 必须有自己的 cron，否则链断了没人发现"
    body = open(os.path.join(WF, 'watchdog-svc.yml')).read()
    assert 'daily_snapshot.json' in body, "应该检查快照产物"
    assert 'generated_at' in body
    assert 'digest-svc.yml' in body, "发现缺快照时应能补跑 digest"


def test_watchdog_runs_before_routine_reads_snapshot():
    """Routine 约 13:30 UTC 读快照。watchdog 必须早于它，补跑才来得及。"""
    _, on = _load('watchdog-svc.yml')
    cron = on['schedule'][0]['cron']
    minute, hour = cron.split()[0], cron.split()[1]
    assert int(hour) < 13 or (int(hour) == 13 and int(minute) == 0), \
        f"watchdog cron {cron} 太晚，赶不上救当天那封信"


def test_daily_cron_heavy_job_stays_manual_only():
    """cron.yml 的 pipeline job 是全量回滚入口，链式触发时不该跑重活。"""
    d, _ = _load('cron.yml')
    assert d['jobs']['pipeline']['if'].strip() == "github.event_name == 'workflow_dispatch'"
