"""US-199：内部人强买入即时提醒。

## 用户妈妈的需求

> 「你看有没有办法捕捉到这个内部人买入，然后就跳出来提醒」
> 「我这个是里面逃出来的这么多股票，然后这个网站又慢，**有的信息就错过了**」

215 只自选股，她不可能每只都点进去看。**信息在系统里，但到不了她眼前。**

## 为什么单推内部人（而不是别的信号）

按五层链（US-179），内部人是**唯一「既快又可信」**的：
A股实测最快 **1 天**就能拿到（US-198 实测更正了我原本「滞后几周」的错误 ——
那是美股 Form 4 的规则）。看到时效力还剩 95%。

## 两道门槛，缺一不可

① **强 cluster**（US-195）：生产实测 15 组「cluster」占股本全部 ≤0.13%，
   其中 600458 是 11 个人合计 **0.000%** —— 员工持股行权，不是看多。
   不设门槛的话这类会天天弹。
② **够新**：超过 14 天不推。一条 2 个月前的强 cluster 已走完大半 alpha。

## 一条纪律：宁可漏，不可吵

这是**额外**的一条微信。**如果它开始每天响，说明门槛错了，
该回来调门槛，而不是让用户学会忽略它。**
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _seed(code, people, ratio_each, shares, price, days_ago=2):
    import db
    db.init_db()
    from radar_app.data.core import get_conn
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    with get_conn() as c:
        c.execute("DELETE FROM insider_changes WHERE code=:c", {"c": code})
        c.execute("INSERT OR IGNORE INTO stocks(code,name,market) VALUES(:c,:c,'cn')",
                  {"c": code})
        for i in range(people):
            c.execute("""INSERT INTO insider_changes(code,holder_name,role,shares,
                avg_price,change_date,ratio_total,ratio_own,reason,fetched_at)
                VALUES(:c,:n,'董事',:s,:p,:d,:r,30,'二级市场买卖',CURRENT_TIMESTAMP)""",
                      {"c": code, "n": f"人{i}", "s": shares, "p": price,
                       "d": d, "r": ratio_each})


# ── 门槛① 赌注够大 ──────────────────────────────────────

def test_weak_cluster_is_not_alerted():
    """妈妈实拍的那种：8 人但合计 0.02% 股本。
    生产上这类占绝大多数 —— 不拦掉就会天天弹。"""
    from scripts.insider_alert import find_alerts
    _seed("900002", 8, 0.003, 100000, 14.5)
    assert find_alerts(codes=["900002"]) == []


def test_strong_cluster_is_alerted():
    from scripts.insider_alert import find_alerts
    _seed("900001", 3, 0.66, 1e7, 20)
    a = find_alerts(codes=["900001"])
    assert len(a) == 1 and a[0]["cluster"]["is_strong"] is True


# ── 门槛② 够新 ──────────────────────────────────────────

def test_old_cluster_is_not_alerted():
    """一条 2 个月前的强 cluster 已经走完大半 alpha（1 个月减半），
    推过去只会让人追高。"""
    from scripts.insider_alert import find_alerts
    _seed("900003", 3, 0.66, 1e7, 20, days_ago=60)
    assert find_alerts(codes=["900003"]) == []


def test_age_threshold_is_two_weeks():
    from scripts.insider_alert import MAX_AGE_DAYS
    assert MAX_AGE_DAYS == 14


# ── 数量上限：真触发很多说明门槛该复查 ──────────────────

def test_run_is_capped():
    from scripts.insider_alert import MAX_PER_RUN
    assert MAX_PER_RUN <= 5, "一次推太多就成了刷屏"


# ── 去重：推过不重推，但追加买入要重推 ──────────────────

def test_dedup_does_not_repeat_the_same_cluster():
    import db
    db.init_db()
    from radar_app.data.push_ledger import (commit_pushed, filter_changed,
                                            state_hash)
    from scripts.insider_alert import find_alerts
    _seed("900001", 3, 0.66, 1e7, 20)
    a = find_alerts(codes=["900001"])[0]
    key = f"insider_cluster:{a['code']}:{a['cluster']['end']}"
    items = [(key, state_hash(a["cluster"]["n_insiders"],
                              a["cluster"]["ratio_total"]), a)]
    ch, _ = filter_changed(1, items)
    assert len(ch) == 1
    commit_pushed(1, ch)
    ch2, un = filter_changed(1, items)
    assert len(ch2) == 0 and un == 1, "推过的不该重推"
    # 追加买入 → 状态变了 → 应该重推
    ch3, _ = filter_changed(1, [(key, state_hash(4, 2.5), a)])
    assert len(ch3) == 1, "追加买入是新信息，要重推"


def test_ledger_is_written_only_after_a_real_push():
    """US-160 的教训：干跑不该吃掉条目，发送失败也不该把条目永久吞掉。"""
    src = open(os.path.join(ROOT, 'scripts', 'insider_alert.py'),
               encoding='utf-8').read()
    i_send = src.index("send_serverchan(key, title, body)")
    i_commit = src.index("commit_pushed(user_id, changed)")
    assert i_send < i_commit, "必须先推送成功再记账"
    dry = src[src.index("if dry:"):i_send]
    assert "commit_pushed" not in dry, "干跑不能记账"


# ── 文案 ────────────────────────────────────────────────

def test_message_explains_why_this_one_deserves_a_push():
    """这是额外的一条微信 —— 必须说清楚「为什么值得单独打扰你」，
    否则它和其它推送没有区别。"""
    from scripts.insider_alert import build_message, find_alerts
    _seed("900001", 3, 0.66, 1e7, 20)
    _t, body = build_message(find_alerts(codes=["900001"]))
    assert "1 天" in body, "要说清 A股 披露有多快（US-198）"
    assert "又快又可信" in body
    assert "衰减" in body or "头一个月" in body, "也要说清它会过期"


def test_no_alerts_is_a_normal_result():
    from scripts.insider_alert import build_message
    assert build_message([]) == (None, None)


# ── 接入流水线 ──────────────────────────────────────────

def test_alert_runs_right_after_insider_refresh():
    """数据刚落库就判断，才谈得上「及时」。"""
    src = open(os.path.join(ROOT, 'radar_app', 'system', 'routes.py'),
               encoding='utf-8').read()
    fn = src[src.index('def trigger_scan():'):]
    fn = fn[:fn.index('@app.route(', 10)] if '@app.route(' in fn[10:] else fn
    assert 'insider_alert' in fn
    assert fn.index('run_insider_refresh') < fn.index('insider_alert'), \
        "提醒必须跑在内部人刷新之后"
