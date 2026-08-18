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


# 链序：fetch → analyze → push → radar → market → Daily Cron → digest
CHAIN = [
    ('fetch-svc.yml',   None),
    ('analyze-svc.yml', 'fetch-svc (US-121)'),
    ('push-svc.yml',    'analyze-svc (US-121)'),
    ('radar-svc.yml',   'push-svc (US-121)'),
    ('market-svc.yml',  'radar-svc (US-121)'),
    ('cron.yml',        'market-svc (US-138)'),
    ('digest-svc.yml',  'Daily Cron'),
]


def test_chain_is_wired_in_order():
    for fname, upstream in CHAIN:
        _, on = _load(fname)
        if upstream is None:
            continue
        wr = on.get('workflow_run')
        assert wr, f"{fname} 应该由 workflow_run 触发"
        assert wr['workflows'] == [upstream], \
            f"{fname} 的上游应是 {upstream}，实际 {wr['workflows']}"


def test_only_fetch_has_a_cron_anchor():
    """多一个 cron 就多一条并行链 —— push-svc 若被 cron 触发会**重复推送给妈妈**。"""
    for fname, upstream in CHAIN:
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
