"""US-163：融券百分比在分母极小时是噪音，不是信号。

2026-08-22 实测：泰晶科技(603738) 报出融券 **+6700%**。
CLAUDE_ROUTINE 那条「绝对值 > 80% 必须写进正文」的强制规则**只看 change_pct
不看分母**，所以这个假象会被原样写成「⚠ 有资金在押注下跌」推给妈妈。

顺带修的第二个问题：快照里 `short_selling.direction` 一直是空串 ——
daily_digest 读的是 `sh.get("direction")`，而 fetch_short_selling_trend
返回的键叫 `trend`。没有代码依赖它（presenter 和 routine 都用 change_pct），
所以不是错误行为，但看到 `direction: ""` 会以为没数据，其实数据在。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.precursor_signals import _SHORT_MIN_BASE_MN


def _judge(earliest, latest):
    """复刻 fetch_short_selling_trend 的分档，不碰网络。"""
    if earliest <= 0:
        return {"valid": False}
    change_pct = round((latest - earliest) / earliest * 100, 1)
    meaningful = earliest >= _SHORT_MIN_BASE_MN and latest >= _SHORT_MIN_BASE_MN
    if not meaningful:
        return {"valid": True, "meaningful": False, "change_pct": change_pct,
                "trend": "中性", "base_short": earliest, "latest_short": latest}
    trend = "做空增加" if change_pct >= 30 else ("做空减少" if change_pct <= -30 else "中性")
    return {"valid": True, "meaningful": True, "change_pct": change_pct,
            "trend": trend, "base_short": earliest, "latest_short": latest}


def test_tiny_base_flagged_not_meaningful():
    """泰晶科技那种情况：0.01万→0.68万股 = +6700%，但两边都可忽略。"""
    r = _judge(0.01, 0.68)
    assert r["change_pct"] == 6700.0
    assert r["meaningful"] is False
    assert r["trend"] == "中性"          # 不许报「做空增加」


def test_tiny_base_still_returns_raw_numbers():
    """必须把原始余量带出去 —— 读的人才有判断依据。
    原来快照只给 change_pct，没人能看出 6700% 是假象。"""
    r = _judge(0.01, 0.68)
    assert r["base_short"] == 0.01
    assert r["latest_short"] == 0.68


def test_real_increase_still_meaningful():
    """药明康德那种：真实量级上的 +33.5% 要照常判「做空增加」。"""
    r = _judge(100.0, 133.5)
    assert r["meaningful"] is True
    assert r["trend"] == "做空增加"


def test_real_decrease_still_meaningful():
    """海康威视那种 −85.8%：跨过 routine 的 ±80% 线，必须是 meaningful。"""
    r = _judge(100.0, 14.2)
    assert r["meaningful"] is True
    assert r["change_pct"] == -85.8
    assert r["trend"] == "做空减少"


def test_boundary_at_threshold():
    assert _judge(_SHORT_MIN_BASE_MN, _SHORT_MIN_BASE_MN)["meaningful"] is True
    assert _judge(_SHORT_MIN_BASE_MN - 0.01, 5.0)["meaningful"] is False


def test_shrink_to_tiny_also_flagged():
    """反向也要挡：从正常量级缩到接近零，百分比同样失真。"""
    r = _judge(50.0, 0.2)
    assert r["meaningful"] is False


def test_zero_base_still_invalid():
    assert _judge(0.0, 10.0)["valid"] is False


def test_snapshot_carries_base_and_meaningful():
    """回归：daily_digest 必须把 base_short / meaningful 带进快照，
    且 direction 要读 trend（不是不存在的 direction 键）。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    src = open(os.path.join(root, 'scripts/daily_digest.py')).read()
    assert '"direction": sh.get("trend", "")' in src
    assert '"base_short": sh.get("base_short")' in src
    assert '"meaningful": sh.get("meaningful", True)' in src


def test_routine_rule_requires_meaningful():
    """CLAUDE_ROUTINE 的强制提示规则必须先看 meaningful。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    doc = open(os.path.join(root, 'CLAUDE_ROUTINE.md')).read()
    i = doc.index('融券背离强制提示规则')
    section = doc[i:i + 900]
    assert 'meaningful' in section
    assert '6700' in section          # 留着实测证据，别让人再踩一次
