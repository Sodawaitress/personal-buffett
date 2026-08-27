"""US-188：行业映射拉不到数据 —— 是那台主机挂了，不是 IP 被封。

## 三层原因，前两层都修过了

行业映射从 2026-08-22 起停在 263 只、覆盖率 59%。查了三轮：

    第一层（US-169）：流水线断链，precursor 那一棒根本没跑     → 已修
    第二层（US-174）：行业映射排第三，被前面的慢活饿死          → 已修
    第三层（本条）  ：**`push2.eastmoney.com` 这台主机 502**

前两层修完之后，错误信息终于说得出真原因：

    industry_em: 板块列表拉取失败（<东财板块列表为空（IP 被封？）>）

## 决定性判据：同一次运行里，一个成一个败

    同一个 Fly IP、同一次 cron_scan：
      industry_em  ❌ 板块列表为空
      precursor    ✅ 成功（63 分钟跑完 215 只）

所以**不是 IP 被封**。再从新西兰住宅 IP 试同一个接口 —— 同样 502。
**两地都失败 = 主机本身的问题。**

## 实测各主机

    push2.eastmoney.com        502（两地一致）
    1./7./19./82.push2         第一发能通、第二发 RemoteDisconnected（按 IP 限流）
    push2delay.eastmoney.com   ✅ 连打 8 发全过

`push2delay` 是**延时行情**主机。对行业分类来说延时毫无影响 ——
我们要的是「这只股票属于哪个板块」，板块归属一天都不会变一次。

实测效果：改主机后本地跑 8 个板块 → **映射 707 只，零失败**（改前 boards=0）。

## 一个会静默出错的差异

`push2` 返回的 `diff` 是**列表**，`push2delay` 返回的是**字典**
（键 `"0"`,`"1"`,`"2"`）。换主机时如果不处理，会拿到**空结果且不报错** ——
正是本仓最怕的那种失败（跑了、没报错、什么也没产出）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _src():
    return open(os.path.join(ROOT, 'scripts', 'industry_signals.py'),
                encoding='utf-8').read()


def test_delay_host_is_the_primary():
    """push2delay 限流宽得多（实测 8/8 vs push2 的「6 发就 502」），
    而且行业分类根本不需要实时。"""
    from scripts.industry_signals import _EM_BASE, _EM_HOSTS
    assert "push2delay" in _EM_HOSTS[0], f"主源应是延时主机，实际 {_EM_HOSTS[0]}"
    assert _EM_BASE == _EM_HOSTS[0]


def test_there_is_a_fallback_chain():
    """单一主机 = 单点故障。这次就是那台主机挂了导致整条线停摆 6 天。"""
    from scripts.industry_signals import _EM_HOSTS
    assert len(_EM_HOSTS) >= 2
    assert len({h.split("//")[1].split("/")[0] for h in _EM_HOSTS}) == len(_EM_HOSTS), \
        "降级链里有重复主机"


def test_falls_over_to_next_host_on_failure():
    src = _src()
    fn = src[src.index('def _em_get('):src.index('def fetch_spot_em')]
    assert 'for base in _EM_HOSTS' in fn, "要逐个主机降级，不能只重试同一台"


def test_empty_200_switches_host_instead_of_being_trusted():
    """200 但 data 为空**不能**当成「这个板块没有成分股」——
    那正是本仓最怕的静默失败：跑了、没报错、什么也没产出。"""
    fn = _src()
    fn = fn[fn.index('def _em_get('):fn.index('def fetch_spot_em')]
    assert 'if items:' in fn, "空结果要换主机，不能直接返回"
    assert '200 但' in fn or 'data 为空' in fn


def test_handles_both_dict_and_list_diff():
    """push2 返回 list、push2delay 返回 dict（键 "0","1","2"）。
    不处理就会静默拿到空结果。"""
    fn = _src()
    fn = fn[fn.index('def _em_get('):fn.index('def fetch_spot_em')]
    assert 'isinstance(diff, dict)' in fn
    assert 'diff.values()' in fn


def test_parses_a_dict_shaped_response():
    """直接喂 push2delay 的真实形状，确认解析得出来。"""
    import types

    import scripts.industry_signals as m

    payload = {"data": {"total": 496, "diff": {
        "0": {"f12": "BK0420", "f14": "航空机场", "f3": -54},
        "1": {"f12": "BK0421", "f14": "铁路公路", "f3": -37},
    }}}

    class _R:
        def raise_for_status(self): pass
        def json(self): return payload

    fake = types.SimpleNamespace(get=lambda *a, **k: _R())
    real = sys.modules.get("requests")
    sys.modules["requests"] = fake
    try:
        items, total = m._em_get("whatever")
    finally:
        if real is not None:
            sys.modules["requests"] = real
    assert total == 496
    assert [i["f14"] for i in items] == ["航空机场", "铁路公路"]


def test_comment_records_why_delay_host_is_acceptable():
    """换成延时数据是个有代价的决定，理由必须写在代码里 ——
    否则后来的人会以为是疏忽，又换回实时主机。"""
    src = _src()
    assert '延时' in src and '板块归属' in src
