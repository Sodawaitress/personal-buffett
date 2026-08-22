"""US-162：日报候选股票的覆盖范围。

生产实测的错配：推送只有**一个收件人**（全局 Server酱 key，妈妈的手机），
但候选股票只来自 `admin_user_id()`：

    id=2  ***@qq.com     198 只  ← 妈妈的实际自选股
    id=4  ***@gmail.com   33 只  ← admin，日报只看这个

所以那 198 只**从来没进过每日「今天有变化的」推送**。她只在五选信里被覆盖，
因为快照的 scope 是 all_users。

顺带记一个我自己犯过两次的错：一开始我以为「推送发给 id=7 那个叫 mom 的账号」，
那是拿**本地旧库**的干跑结果当生产事实 —— 和之前拿本地库判数据停更是同一个错。
生产实测：所有 8 个账号的 notify_daily 和 webhook 都是 0，没有任何人配个人推送。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _digest_ids(primary, env_val):
    """复刻 digest_user_ids 的解析，不碰环境变量。"""
    ids = [primary]
    for part in (env_val or "").replace("，", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids


def test_default_is_admin_only():
    """不设环境变量时保持原行为 —— 改覆盖范围要显式声明。"""
    assert _digest_ids(4, "") == [4]
    assert _digest_ids(4, None) == [4]


def test_extra_account_added():
    assert _digest_ids(4, "2") == [4, 2]


def test_multiple_and_whitespace():
    assert _digest_ids(4, " 2, 5 ,8 ") == [4, 2, 5, 8]


def test_full_width_comma_tolerated():
    """中文输入法逗号是个真实的踩坑点。"""
    assert _digest_ids(4, "2，5") == [4, 2, 5]


def test_primary_not_duplicated():
    assert _digest_ids(4, "4,2") == [4, 2]


def test_garbage_ignored():
    """脏值不该让整个推送挂掉 —— 忽略比抛异常安全。"""
    assert _digest_ids(4, "abc, ,2, -1, 3x") == [4, 2]


def test_signature_accepts_extra_ids():
    """回归：build_user_push_payload 必须能接受额外账号，
    且台账仍记在收件人（第一个参数）名下 —— 台账跟的是「谁被打扰过」，
    不是股票的主人。"""
    import inspect

    from scripts import stock_report
    sig = inspect.signature(stock_report.build_user_push_payload)
    assert list(sig.parameters) == ["user_id", "date_str", "extra_user_ids"]
    src = inspect.getsource(stock_report.build_user_push_payload)
    assert "for uid in [user_id, *extra_user_ids]" in src
    # 台账用的仍是 user_id，不是并集里的其它人
    assert "filter_changed(user_id," in src


def test_workflow_declares_the_extra_account():
    """push-svc.yml 必须显式声明 DIGEST_USER_IDS，否则改了代码也没生效。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    body = open(os.path.join(root, '.github/workflows/push-svc.yml')).read()
    assert 'DIGEST_USER_IDS' in body
