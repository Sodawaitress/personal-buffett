"""US-160：推送去重 —— 「今天该注意的」每天内容几乎一样。

根因不是硬编码（用户猜是 POP MART 写死了，查过：POP MART 只出现在搜索
别名表里，分析结果是真的）。真正原因是**五个板块里有四个取的是当前状态，
不是今日事件**：

    早期预警  get_stock_events 无任何日期过滤 → 一个月前的预警天天推
    机构领先  get_signal_conclusion = 当前结论 → 结论不变就天天播
    机构脚印  latest_dir = 当前趋势 → 趋势持续就天天播
    催化剂    未来 7 天窗口 → 同一件事连播 7 天
    评级变化  真事件，但 45% 的股票不是每天分析，变化会跨天残留

而系统此前**完全没有任何推送去重机制**。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from radar_app.data.push_ledger import state_hash


# ── 指纹 ────────────────────────────────────────────────

def test_same_content_same_hash():
    assert state_hash("机构在建仓") == state_hash("机构在建仓")


def test_different_content_different_hash():
    assert state_hash("机构在建仓") != state_hash("机构在出货")


def test_none_and_empty_equivalent():
    """None 与空串必须等价，否则会制造无意义的「变化」而重复打扰。"""
    assert state_hash(None) == state_hash("")
    assert state_hash("a", None) == state_hash("a", "")


def test_multipart_order_matters():
    assert state_hash("A", "B") != state_hash("B", "A")


# ── 变化判定（复刻 filter_changed 的语义，不碰 DB）──────────

def _filter(seen, items):
    changed, unchanged = [], 0
    for key, sh, payload in items:
        if seen.get(key) != sh:
            changed.append((key, sh, payload))
        else:
            unchanged += 1
    return changed, unchanged


def test_first_time_everything_is_new():
    ch, un = _filter({}, [("lead:600519", "h1", "x"), ("prophet:300124", "h2", "y")])
    assert len(ch) == 2 and un == 0


def test_unchanged_state_is_suppressed():
    """核心：结论没变就不该再推 —— 这正是「每天一样」的解药。"""
    seen = {"lead:600519": "h1"}
    ch, un = _filter(seen, [("lead:600519", "h1", "x")])
    assert ch == [] and un == 1


def test_changed_state_pushes_again():
    """机构结论从「建仓」变「出货」是真信号，必须再推。"""
    seen = {"lead:600519": "h1"}
    ch, un = _filter(seen, [("lead:600519", "h2", "改口了")])
    assert len(ch) == 1 and un == 0
    assert ch[0][2] == "改口了"


def test_new_identity_pushes_even_if_others_unchanged():
    seen = {"lead:600519": "h1"}
    ch, un = _filter(seen, [("lead:600519", "h1", "老的"),
                            ("lead:000001", "h9", "新的")])
    assert [c[2] for c in ch] == ["新的"]
    assert un == 1


# ── 催化剂：身份含日期，状态分「临近/还早」───────────────

def _catalyst_key(code, etype, edate):
    return f"catalyst:{code}:{etype}:{edate}"


def _catalyst_state(days_until):
    return "imminent" if (days_until if days_until is not None else 9) <= 1 else "far"


def test_same_catalyst_not_repeated_daily():
    """同一件解禁事件在 7 天窗口里会被扫到 7 次，只该推 1 次。"""
    k = _catalyst_key("600519", "share_unlock", "2026-08-25")
    seen = {k: _catalyst_state(6)}
    ch, un = _filter(seen, [(k, _catalyst_state(5), "5天后解禁")])
    assert ch == [] and un == 1


def test_catalyst_reminds_when_imminent():
    """临近（≤1天）时状态从 far → imminent，值得再提醒一次。
    这是有价值的重复，不是噪音。"""
    k = _catalyst_key("600519", "share_unlock", "2026-08-25")
    seen = {k: _catalyst_state(5)}
    ch, un = _filter(seen, [(k, _catalyst_state(1), "1天后解禁")])
    assert len(ch) == 1


def test_different_catalyst_dates_are_different_events():
    """同一只股票的两次解禁是两件事，各推各的。"""
    a = _catalyst_key("600519", "share_unlock", "2026-08-25")
    b = _catalyst_key("600519", "share_unlock", "2026-09-25")
    assert a != b


# ── 早期预警的日期窗口（原来完全没有）────────────────────

def _within_window(event_date, cutoff):
    return str(event_date or "")[:10] >= cutoff


def test_old_early_warning_excluded():
    """原来 get_stock_events 不做日期过滤，一个月前的预警也当「今天该注意的」。"""
    assert _within_window("2026-07-01", "2026-08-05") is False


def test_recent_early_warning_included():
    assert _within_window("2026-08-18", "2026-08-05") is True


def test_missing_event_date_excluded():
    """没有日期的事件不该混进来 —— 无法判断新旧就不推。"""
    assert _within_window("", "2026-08-05") is False


# ── 两阶段：干跑/失败不该吃掉条目 ─────────────────────────

def test_payload_returns_pending_separately():
    """build_user_push_payload 必须返回 (正文, 待记账)，
    记账由调用方在**发送成功后**做 —— 否则干跑会静默吃掉条目，
    发送失败会让这件事再也不提醒。"""
    import inspect

    from scripts import stock_report
    sig = inspect.signature(stock_report.build_user_push_payload)
    # 前两个参数固定；US-162 之后可以有额外的 extra_user_ids
    assert list(sig.parameters)[:2] == ["user_id", "date_str"]
    src = inspect.getsource(stock_report.build_user_push_payload)
    assert "return \"\\n\".join(lines), changed" in src
    assert "commit_pushed" not in src        # 这个函数绝不能自己记账
