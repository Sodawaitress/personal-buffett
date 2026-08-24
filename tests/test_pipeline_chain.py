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
# US-169（2026-08-25）：SEG2 内部原本还用 workflow_run 串，实测**一次都没生效**。
# 原因是 GitHub 的防递归规则：
#   "When you use the repository's GITHUB_TOKEN to perform tasks, events
#    triggered by the GITHUB_TOKEN will not create a new workflow run."
# radar→market 的桥接用的正是 GITHUB_TOKEN，所以 market 跑完不发 workflow_run
# 事件，cron 永远等不到。US-150 的桥接修好了第 4 层，却在第 5 层制造了
# 一模一样的静默断链。
#
# 实测证据（GHA 运行历史）：
#   08-24  radar ✅ → market ✅(dispatch) → cron ❌ 从未触发
#   08-22  人手动 dispatch cron → digest ✅ workflow_run 正常
#   → 人触发会发事件，GITHUB_TOKEN 触发不会。
#
# 后果：东财行业映射搭的是 cron 的 light job，8/22 之后一条新映射都没有，
# 自选股行业覆盖率永久卡在 60%。
#
# 所以 SEG2 全段改成显式 dispatch 桥接，链上不再有任何 workflow_run。
SEG2 = [
    ('market-svc.yml',  None),   # 由 radar 桥接 dispatch
    ('cron.yml',        None),   # 由 market 桥接 dispatch
    ('digest-svc.yml',  None),   # 由 cron 的 light job 桥接 dispatch
]

# 每一跳桥接：(上游文件, 下游文件名)
BRIDGES = [
    ('radar-svc.yml',  'market-svc.yml'),
    ('market-svc.yml', 'cron.yml'),
    ('cron.yml',       'digest-svc.yml'),
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


def test_every_bridge_exists():
    """每一跳桥接都必须显式存在，否则下游永远不会启动。"""
    for up, down in BRIDGES:
        body = open(os.path.join(WF, up)).read()
        assert f'gh workflow run {down}' in body, \
            f"{up} 末尾必须 dispatch {down}"
        assert 'if: always()' in body, f"{up} 的桥接要 always()，上游挂了也放行下游"


def test_every_bridging_workflow_has_actions_write():
    """少了 actions: write，`gh workflow run` 会 403 —— 而且是在
    「Alert on failure」之后的步骤里，告警都不一定发得出来。"""
    for up, _down in BRIDGES:
        d, _ = _load(up)
        ok = any((j.get('permissions') or {}).get('actions') == 'write'
                 for j in d['jobs'].values())
        assert ok, f"{up} 需要某个 job 带 actions: write 才能桥接"


def _workflow_names():
    """文件名 → workflow 的 name: 字段（workflow_run 引用的是 name，不是文件名）。"""
    out = {}
    for fn in os.listdir(WF):
        if fn.endswith(('.yml', '.yaml')):
            try:
                d, _ = _load(fn)
                if isinstance(d, dict) and d.get('name'):
                    out[fn] = d['name']
            except Exception:
                pass
    return out


def test_nothing_listens_via_workflow_run_to_a_bridge_dispatched_workflow():
    """本条守的就是 US-169 那次静默断链，而且是**唯一**抓得到它的形式。

    GitHub 防递归规则：GITHUB_TOKEN 发起的 dispatch，被触发的 workflow
    跑完**不会**再发出 workflow_run 事件。所以只要 X 是被桥接 dispatch
    起来的，任何 `workflow_run: workflows: [X 的 name]` 都等于没接线。

    US-150 的桥接修好了第 4 层（radar→market），但 cron.yml 仍然写着
    workflow_run on "market-svc (US-138)" —— 于是断链原样搬到了第 5 层，
    从 08-19 起 SEG2 一次都没自动跑过。当时的三条测试（链序、嵌套深度、
    cron 锚点唯一）全绿。

    实测证据：
      08-24  radar ✅ → market ✅(dispatch) → cron ❌ 从未触发
      08-22  人手动 dispatch cron → digest ✅ workflow_run 正常
    """
    names = _workflow_names()
    dispatched = {names[down] for _up, down in BRIDGES if down in names}
    for fname, wf_name in names.items():
        _, on = _load(fname)
        wr = on.get('workflow_run') or {}
        for up_name in (wr.get('workflows') or []):
            assert up_name not in dispatched, (
                f"{fname} 用 workflow_run 监听 '{up_name}'，但 '{up_name}' 是被"
                f" GITHUB_TOKEN 桥接 dispatch 起来的 —— 它跑完不会发 workflow_run"
                f" 事件，{fname} 永远等不到。改成让上游显式 dispatch 它。")


def test_segment2_is_dispatch_only():
    """SEG2 全段靠 dispatch 串。任何一环改回 workflow_run 都会静默断链。"""
    for fname, _ in SEG2:
        _, on = _load(fname)
        assert 'workflow_dispatch' in on, f"{fname} 必须能被 dispatch"


def test_every_chain_workflow_can_actually_be_reached():
    """最朴素也最该有的一条：链上每个 workflow 都必须有**某种**自动到达的
    方式 —— cron 锚点、workflow_run、或上游的桥接 dispatch。

    US-169 的 market-svc 三样都没有（只有 workflow_dispatch，schedule 在
    US-150 里被删了，workflow_run 因深度上限不能加，桥接当时还没接到它
    下游）。测试全绿，链条却断着。
    """
    bridged = {down for _up, down in BRIDGES}
    for fname, upstream in CHAIN:
        _, on = _load(fname)
        reachable = ('schedule' in on) or ('workflow_run' in on) or (fname in bridged)
        assert reachable, (
            f"{fname} 没有任何自动触发方式：没有 cron 锚点、没有 workflow_run、"
            f"也没有上游桥接 dispatch 它 —— 它只会在有人手动点的时候跑")


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
