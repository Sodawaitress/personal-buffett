"""US-170：流水线编排的结构守卫。

## 两次静默断链的完整教训

七个服务原本用 `workflow_run` 首尾相接。那是**事件通知**原语，GitHub 在它
上面装了两道防递归闸，而这两道闸的存在意义恰恰就是阻止用 workflow 链成
流水线：

  ① 最多串三层。US-150 撞上：market 在第 4 层，静默不跑。
  ② GITHUB_TOKEN 触发的运行，跑完**不发** workflow_run 事件。
     US-169 撞上：① 的修法（用 GITHUB_TOKEN dispatch 桥接）正好触发 ②，
     断链原样搬到第 5 层，从 08-19 起整个 SEG2 一次都没自动跑过。

两次不是巧合，是**耦合**：绕开 ① 只能改用 dispatch，改用 dispatch 就必然
撞上 ②。逃出一个正好掉进另一个。

## 为什么当时的测试全绿

US-150 留了三条守卫：链序、嵌套深度、cron 锚点唯一。**全通过。**
因为它们查的是「线接得对不对」—— 而线确实接对了，`cron.yml` 里明明白白
写着 `workflow_run: ["market-svc (US-138)"]`，名字一个字都不差。
没有一条在问「**这个事件到底发不发得出来**」。

真正找出问题的不是任何测试，是去翻生产的运行历史，看每个 workflow
上一次**自动**跑是什么时候。所以下面除了结构断言，还钉住了那些
「文档没写、只能实测」的行为（见 test_documents_measured_workflow_call_facts）。

## 现在的形状

`pipeline.yml` 用 `workflow_call` 顺序调用七个可重用工作流。
`workflow_call` 是**函数调用**原语：10 层上限、无 token 规则、
整条链是一次 run（实测 github.run_id 与调用方相同）。
"""
import os
import re

import yaml

ROOT = os.path.join(os.path.dirname(__file__), '..')
WF = os.path.join(ROOT, '.github', 'workflows')

ORCHESTRATOR = 'pipeline.yml'

# 编排顺序：每一棒的 job 名 → 被调用的可重用工作流
CHAIN = [
    ('fetch',     'fetch-svc.yml'),
    ('analyze',   'analyze-svc.yml'),
    ('push',      'push-svc.yml'),
    ('radar',     'radar-svc.yml'),
    ('market',    'market-svc.yml'),
    ('precursor', 'precursor-svc.yml'),
    ('digest',    'digest-svc.yml'),
]


def _load(name):
    with open(os.path.join(WF, name)) as f:
        d = yaml.safe_load(f)
    # PyYAML 把裸 `on:` 解析成布尔 True
    return d, (d.get(True) or d.get('on') or {})


def _all_workflow_files():
    # 跳过 macOS 在外置卷上生成的 `._` 影子文件（本地产物，不在仓库里）
    return [f for f in os.listdir(WF)
            if f.endswith(('.yml', '.yaml')) and not f.startswith('.')]


# ── 编排结构 ────────────────────────────────────────────

def test_orchestrator_calls_every_service_in_order():
    d, _ = _load(ORCHESTRATOR)
    jobs = d['jobs']
    for i, (job, svc) in enumerate(CHAIN):
        assert job in jobs, f"编排器缺少 {job}"
        assert jobs[job]['uses'].endswith(svc), \
            f"{job} 应调用 {svc}，实际 {jobs[job]['uses']}"
        if i == 0:
            assert not jobs[job].get('needs'), "第一棒不该有 needs"
        else:
            prev = CHAIN[i - 1][0]
            assert jobs[job].get('needs') == prev, \
                f"{job} 的上游应是 {prev}，实际 {jobs[job].get('needs')}"


def test_failure_propagates_but_does_not_block():
    """原语义：上游 failure 仍放行（各服务互相独立，analyze 挂了也该把已有
    报告推出去），只有**被取消**才中断整条链。`!cancelled()` 精确复刻它。

    写成 always() 就错了 —— 那样连「用户主动取消」都拦不住。
    """
    d, _ = _load(ORCHESTRATOR)
    for job, _svc in CHAIN[1:]:
        cond = str(d['jobs'][job].get('if', ''))
        assert 'cancelled()' in cond and cond.strip().startswith('${{ !'), \
            f"{job} 的 if 应为 !cancelled()，实际 {cond!r}"


def test_secrets_are_inherited_by_every_call():
    """可重用工作流拿不到调用方的 env（官方文档明写），secrets 也必须显式
    inherit。漏一个就是「跑了、没报错、什么也没干」。"""
    d, _ = _load(ORCHESTRATOR)
    for job, _svc in CHAIN:
        assert d['jobs'][job].get('secrets') == 'inherit', \
            f"{job} 缺 secrets: inherit"


# ── 反向守卫：不许退回旧原语 ────────────────────────────

def test_no_workflow_run_anywhere_in_the_chain():
    """链上任何一环用回 workflow_run，就会重演 US-150 / US-169。"""
    for _job, svc in CHAIN:
        _, on = _load(svc)
        assert 'workflow_run' not in on, f"{svc} 不该有 workflow_run"
    _, on = _load(ORCHESTRATOR)
    assert 'workflow_run' not in on


def test_no_bridge_dispatch_left_in_the_chain():
    """`gh workflow run` 桥接是 US-169 的病灶本身（GITHUB_TOKEN 触发的运行
    不发事件）。编排器接管后不该再有任何一处。

    查的是**真实步骤**，不是全文匹配 —— 注释里复盘那段历史是应该保留的。
    """
    for _job, svc in CHAIN + [(None, ORCHESTRATOR)]:
        d, _ = _load(svc)
        for jname, job in (d.get('jobs') or {}).items():
            for step in (job.get('steps') or []):
                run = str(step.get('run', ''))
                assert 'gh workflow run' not in run, \
                    f"{svc}:{jname} 仍有桥接 dispatch —— 编排器已接管，删掉"


def test_every_service_is_callable_and_still_manually_runnable():
    _, orch_on = _load(ORCHESTRATOR)
    for _job, svc in CHAIN:
        _, on = _load(svc)
        assert 'workflow_call' in on, f"{svc} 必须可被 workflow_call 调用"
        assert 'workflow_dispatch' in on, \
            f"{svc} 要保留 workflow_dispatch —— 单独补跑一棒不该跑全链"


def test_no_chain_service_has_its_own_cron():
    """多一个 cron 就多一条并行链。US-150 的「双跑 digest」就是这么来的：
    08-18 workflow_run 14:43 + schedule 14:53 各跑一次，还发过一封假警报。

    只管链上的服务 —— 仓库里别的 workflow（提醒、体检、看门狗）自己排班
    是它们的事，与流水线无关。
    """
    for _job, svc in CHAIN:
        _, on = _load(svc)
        assert 'schedule' not in on, \
            f"{svc} 自己排了 cron —— 会和编排器跑出两条并行链"


def test_orchestrator_has_exactly_one_cron():
    d, on = _load(ORCHESTRATOR)
    crons = on.get('schedule') or []
    assert len(crons) == 1, f"编排器应只有一条 cron，实际 {crons}"


def test_nothing_else_calls_a_chain_service():
    """链上的服务只该由编排器调用。别处再 uses: 一遍就会多跑一次
    （包括多推一次给妈妈）。"""
    chain_files = {svc for _j, svc in CHAIN}
    for f in _all_workflow_files():
        if f == ORCHESTRATOR:
            continue
        d, _ = _load(f)
        for jname, job in (d.get('jobs') or {}).items():
            uses = str(job.get('uses', ''))
            hit = next((c for c in chain_files if uses.endswith(c)), None)
            assert not hit, f"{f}:{jname} 也在调用 {hit} —— 只有编排器该调用它"


def test_orchestrator_serializes_runs():
    """手动触发撞上定时触发会跑出两条并行全链 —— 包括两次推送给妈妈。"""
    d, _ = _load(ORCHESTRATOR)
    conc = d.get('concurrency') or {}
    assert conc.get('group'), "编排器需要 concurrency group"
    assert conc.get('cancel-in-progress') is False, \
        "不能 cancel-in-progress —— 跑到一半被腰斩比排队更糟"


# ── 那些「文档没写、只能实测」的事实 ────────────────────

def test_documents_measured_workflow_call_facts():
    """2026-08-25 用临时探针实测（官方文档未载明）：

        github.event_name  = 调用方的事件（workflow_dispatch），不是 workflow_call
        github.workflow    = 调用方的名字
        github.run_id      = 与调用方相同（整条链是一次 run）
        secrets: inherit   = 生效
        needs.<job>.result = 可读

    第一条是陷阱：任何写在被调用方里的 `github.event_name == ...` 判断，
    读到的都是调用方的事件。cron.yml 的重型 pipeline 作业正是靠
    `if: github.event_name == 'workflow_dispatch'` 保持手动专用 ——
    留在链上的话，编排器一被手动触发就会把它一起带起来。
    所以 US-170 把它拆出了链条。
    """
    for _job, svc in CHAIN:
        body = open(os.path.join(WF, svc)).read()
        # 只看真正的 if 条件，不管注释
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            assert 'github.event_name' not in stripped, (
                f"{svc} 仍靠 github.event_name 做判断 —— 被调用时它是**调用方**"
                f"的事件，语义会悄悄反转：{stripped!r}")


def test_retired_monolith_stays_off_the_chain():
    """cron.yml 现在只剩退役 monolith 的手动回滚入口。它绝不能回到链上 ——
    它的 `if: github.event_name == 'workflow_dispatch'` 在 workflow_call 下
    会读到调用方的事件（实测），编排器一手动触发就会跑起全量重跑。"""
    _, on = _load('cron.yml')
    assert 'workflow_call' not in on, "cron.yml 不能可被调用"
    assert 'schedule' not in on, "cron.yml 不能排班"
    assert list(on.keys()) == ['workflow_dispatch'], \
        f"cron.yml 应只有 workflow_dispatch，实际 {list(on.keys())}"
    d, _ = _load(ORCHESTRATOR)
    for job in d['jobs'].values():
        assert 'cron.yml' not in str(job.get('uses', '')), \
            "编排器不该调用 cron.yml"


# ── 推送安全（妈妈的信） ────────────────────────────────

def test_skip_push_cannot_silently_disable_the_letter():
    """scripts/svc_push.py 用 bool(os.environ.get('SKIP_PUSH')) ——
    **任何非空串都为真，'0' 也为真**。所以 SKIP_PUSH 必须产出空串，
    编排器也绝不能传 skip_push: '0'。传了 = 妈妈的信静默停掉。
    """
    body = open(os.path.join(WF, 'push-svc.yml')).read()
    m = re.search(r'^\s*SKIP_PUSH:\s*(.+)$', body, re.M)
    assert m, "push-svc 应显式设置 SKIP_PUSH"
    expr = m.group(1)
    assert "'1'" in expr and "''" in expr, \
        f"SKIP_PUSH 应只在显式 '1' 时干跑，否则空串：{expr!r}"
    assert 'github.event.inputs' not in expr, \
        "被调用时 github.event.inputs 指向调用方的输入，要用 `inputs` 上下文"

    d, _ = _load(ORCHESTRATOR)
    with_ = d['jobs']['push'].get('with') or {}
    assert 'skip_push' not in with_, \
        "编排器不能传 skip_push —— 传任何非空值（含 '0'）都会停掉推送"

    src = open(os.path.join(ROOT, 'scripts', 'svc_push.py')).read()
    assert 'bool(os.environ.get("SKIP_PUSH"))' in src, \
        "svc_push 的判据变了就来更新本测试的前提"


# ── 看门狗 ──────────────────────────────────────────────

def test_watchdog_checks_artifact_not_task_status():
    """本仓的招牌失败模式是「跑了、返回了、没报错、什么也没产出」，
    所以兜底必须查**产物**，不能查任务状态。"""
    body = open(os.path.join(WF, 'watchdog-svc.yml')).read()
    assert 'snapshot' in body.lower(), "看门狗应检查快照产物"
    assert 'gh workflow run' in body, "看门狗要能补跑"
