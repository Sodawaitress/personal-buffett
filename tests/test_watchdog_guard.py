"""US-210：「没有快照」和「链条断了」是两回事。

watchdog 原本的判据只有一条 ——「今天的快照 commit 了吗」，
注释里写着前提：「链条正常时 digest 约 11:36 UTC 就完成了」。

**那个前提在 2026-08-27 之后没了。** GHA 定时事件每天固定晚约 4.75 小时
放行（US-206 实测），pipeline 12:08 起跑、16:45 才结束。
于是 watchdog 每天都看到「今天没快照」，判定断链、补跑 digest ——
而 pipeline 自己的 digest 正在排队。

实测后果（`git log --grep="daily snapshot"`）：

    08-28  2 次  ⚠️
    09-02  2 次  ⚠️
    09-04  2 次  ⚠️   且 pipeline 的 digest 被判 cancelled

**这正是 US-150「双跑 digest」那个 bug 从另一扇门回来。**
US-150 的教训写的是「别加 cron」，但双跑其实不需要新 cron ——
一个判据过时的兜底任务就够了。

修法沿用 US-149 给 Routine 定的那条区分：
**先看上游是不是还在动，再判它是不是挂了。**
"""
import re

import pytest

WF = ".github/workflows/watchdog-svc.yml"


def _txt():
    return open(WF, encoding="utf-8").read()


def test_watchdog_checks_whether_pipeline_is_still_running():
    s = _txt()
    assert "in_progress" in s and "queued" in s, \
        "watchdog 没有检查上游是否在途，会把「慢一步」判成「断了」"


def test_recovery_requires_both_conditions():
    """补跑的条件必须是**两个都满足**：今天没快照 **且** 上游没有在途任务。
    少一个就会重演双跑。"""
    s = _txt()
    guards = re.findall(r"if:\s*(steps\.[^\n]+)", s)
    recov = [g for g in guards if "fresh" in g]
    assert recov, "找不到补跑的条件"
    for g in recov:
        assert "in_flight" in g, f"补跑条件缺少在途检查: {g}"
        assert "&&" in g, f"两个条件不是「与」关系: {g}"


def test_alert_is_also_gated():
    """告警也要挂同样的条件 —— 否则每天推一条假的「链条断了」给用户，
    而真断的那天就没人信了。"""
    s = _txt()
    alert = s[s.index("- name: Alert"):]
    cond = re.search(r"if:\s*([^\n]+)", alert)
    assert cond and "in_flight" in cond.group(1), "告警没挂在途检查，会天天误报"


def test_pipeline_remains_the_only_cron_anchor():
    """US-150 的老规矩没有被这次改动破坏：链上的服务不许各自排 cron。"""
    import glob
    offenders = []
    for f in glob.glob(".github/workflows/*-svc.yml"):
        t = open(f, encoding="utf-8").read()
        if re.search(r"^\s*-\s*cron:", t, re.M) and "watchdog" not in f \
                and "audit" not in f and "industry-map" not in f:
            offenders.append(f)
    assert not offenders, f"链上服务加了 cron，会多出并行链: {offenders}"
