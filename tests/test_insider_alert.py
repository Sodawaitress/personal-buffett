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
    """人数够、但**赌注两条都不够**（占股本 0.02%、金额约 232 万）。
    生产上这类占绝大多数 —— 不拦掉就会天天弹。

    注：US-200 把金额门槛从 5000 万降到 1000 万（研究下限是 250-400 万），
    所以样本金额也跟着调小，才落在「弱」这一档。"""
    from scripts.insider_alert import find_alerts
    _seed("900002", 8, 0.003, 20000, 14.5)
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
    from radar_app.data.core import get_conn
    from scripts.insider_alert import find_alerts
    _seed("900001", 3, 0.66, 1e7, 20)
    a = find_alerts(codes=["900001"])[0]
    key = f"insider_cluster:{a['code']}:{a['cluster']['end']}"
    # 每次从干净状态开始 —— 上一次跑留下的记账会让「第一次」变成「推过了」
    with get_conn() as c:
        c.execute("DELETE FROM push_ledger WHERE item_key = :k", {"k": key})
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


# ══ US-200：查文献后修正的两处 ══════════════════════════

def test_equity_incentive_is_never_opportunistic_no_matter_the_size():
    """原来写的是 `routine_reason and not big` —— **只要金额够大，
    股权激励行权也会被当成主动增持**。那是机制层面的错。

    股权激励/员工持股 与 主动增持的区别**不在金额，在性质**：

        股权激励：按预设条件行权，有强制业绩考核，价格往往低于市价 ——
                  行不行权取决于解锁条件和个人税务，不取决于他此刻怎么看公司
        主动增持：自掏腰包按市价买 —— 才是「我看好，我下注」

    **一次 2 亿的股权激励行权，说明的是「三年前定的考核达标了」，
    不是「他今天觉得便宜」。金额再大也换不来这个含义。**
    """
    from scripts.insider_moves import classify_insider_move as f
    for reason in ("股权激励行权", "员工持股计划", "限制性股票归属",
                   "激励对象获授", "回购注销"):
        c = f(1e7, 0.5, 30, reason, "董事长", 20)      # 2 亿，占股本 0.5%
        assert c["kind"] == "routine", f"{reason} 不该判成主动增持"


def test_real_open_market_buying_still_counts():
    """不能矫枉过正 —— 自掏腰包按市价买的必须仍然算数。"""
    from scripts.insider_moves import classify_insider_move as f
    for reason in ("二级市场买卖", "大宗交易", "集中竞价"):
        assert f(1e7, 0.5, 30, reason, "董事长", 20)["kind"] == "opportunistic"


def test_thresholds_follow_the_evidence_not_a_guess():
    """我第一版拍了「0.5% 股本 或 **5000 万**」——查完文献发现太高。

    实证（高管增持事件策略）：
      · 增持金额下限 **250万–400万** 就有可用信号，年化超额约 22%
      · 金额下限越高，最优持有期越长（250万→10日 / 300万→30日 / 400万→45日）
      · 董监高增持公告后 90 日平均超额 **+3.8%**，显著高于个人和公司股东

    取 1000 万 = 研究下限 400 万的 2.5 倍 —— 我们要的是
    「值得单独推一条微信」的强信号，不是「有统计价值」的边缘信号。
    """
    from scripts.insider_moves import CLUSTER_MIN_AMOUNT, CLUSTER_MIN_RATIO
    assert CLUSTER_MIN_AMOUNT == 1e7, "5000 万太高，研究下限是 250-400 万"
    assert CLUSTER_MIN_RATIO == 0.3
    src = open(os.path.join(ROOT, 'scripts', 'insider_moves.py'),
               encoding='utf-8').read()
    assert "250万" in src and "400万" in src, "门槛的来历要写在代码里"


def test_amount_alone_cannot_promote_a_routine_trade():
    """光有金额不够 —— 妈妈那条 1160 万够金额门槛了，但它是员工持股性质。
    两道关卡必须都过：先判性质（不是机制性交易），再看赌注。"""
    from scripts.insider_moves import describe_insider_activity
    r = describe_insider_activity([
        {"holder_name": f"人{i}", "shares": 100000, "ratio_total": 0.003,
         "ratio_own": 20, "avg_price": 14.5, "change_date": "2026-08-26",
         "reason": "员工持股计划", "role": "高管"} for i in range(8)])
    assert not (r.get("cluster") or {}), "机制性交易根本不该形成 cluster"
