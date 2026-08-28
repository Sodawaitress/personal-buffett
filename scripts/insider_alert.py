"""内部人强买入即时提醒（US-199）。

## 用户妈妈的需求

> 「你看有没有办法捕捉到这个内部人买入，然后就跳出来提醒」
> 「我这个是里面逃出来的这么多股票，然后这个网站又慢，**有的信息就错过了**」

215 只自选股，她不可能每只都点进去看。**信息在系统里，但到不了她眼前。**

## 为什么内部人值得单独推（而别的信号不值得）

按 US-179 的五层链，内部人是**唯一「既快又可信」**的：

    第1层 自己人    A股实测最快 **1 天**就能拿到（US-198 实测）
    第2层 机构      季报/调研，季度频率
    第3层 市场的钱  当天，但噪音大

而且 US-198 更正了一个关键前提：我原本以为「公告滞后几周」——
那是**美股 Form 4** 的规则。A股披露快得多，**看到时效力还剩 95%**。

所以这条信号**值得也来得及**单独推。

## 两道门槛，缺一不可

**① 必须是强 cluster**（US-195）：多人 + 赌注够大。

生产实测过去三个月 15 组「cluster」占股本全部 ≤0.13%，
其中 600458 是 **11 个人合计 0.000%** —— 那是员工持股行权，不是看多。
**不设门槛的话，这类会天天弹，很快就和其它推送一样被忽略。**

**② 必须够新**：超过 `MAX_AGE_DAYS` 不推。
一条 2 个月前的强 cluster 已经走完大半 alpha（1 个月减半），
推过去只会让人追高。

## 一条纪律：宁可漏，不可吵

这是**额外**的一条微信，不和每日五选混在一起。所以它必须稀有 ——
按生产数据估计一个月一两条。**如果它开始每天响，就说明门槛错了，
该回来调门槛，而不是让用户学会忽略它。**
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 交易发生后多少天内才值得提醒（alpha 一个月减半，两周是个保守线）
MAX_AGE_DAYS = int(os.environ.get("INSIDER_ALERT_MAX_AGE", "14"))
# 一次最多提醒几只 —— 真触发这么多只，说明门槛需要复查，而不是刷屏
MAX_PER_RUN = int(os.environ.get("INSIDER_ALERT_MAX", "3"))


def find_alerts(codes=None, max_age_days: int = None) -> list:
    """扫出值得提醒的强 cluster。返回 [] 是**正常结果**，不是故障。"""
    from datetime import date, timedelta

    import db
    from scripts.insider_moves import WINDOW_DAYS, describe_insider_activity

    age = max_age_days or MAX_AGE_DAYS
    cutoff = (date.today() - timedelta(days=age)).isoformat()
    if codes is None:
        codes = [c for c, _ in db.get_all_cn_watchlist_stocks()]

    out = []
    for code in codes:
        try:
            moves = db.get_insider_changes(code, days=WINDOW_DAYS)
        except Exception:
            continue
        if not moves:
            continue
        d = describe_insider_activity(moves)
        cl = d.get("cluster") or {}
        # 门槛①：必须是强 cluster（赌注够大，不只是人多）
        if not cl.get("is_strong"):
            continue
        # 门槛②：必须够新
        if str(cl.get("end") or "") < cutoff:
            continue
        out.append({
            "code": code,
            "name": (moves[0].get("name") if isinstance(moves[0], dict) else None)
                    or _name_of(code),
            "cluster": cl,
            "note": d.get("cluster_note", ""),
            "days_since": d.get("days_since"),
            "decay": d.get("decay") or {},
        })
    # 赌注大的排前面
    out.sort(key=lambda x: -(x["cluster"].get("ratio_total") or 0))
    return out[:MAX_PER_RUN]


def _name_of(code):
    try:
        import db
        s = db.get_stock(code) or {}
        return s.get("name_cn") or s.get("name") or code
    except Exception:
        return code


def build_message(alerts: list) -> tuple:
    """→ (标题, 正文)。空列表返回 (None, None)。"""
    if not alerts:
        return None, None
    n = len(alerts)
    title = (f"自己人在买 · {alerts[0]['name']}" if n == 1
             else f"自己人在买 · {n} 只")
    lines = ["公司里的人自己掏钱买了自家股票，而且是多人一起买。\n"]
    for a in alerts:
        cl = a["cluster"]
        lines.append(f"━━ {a['name']}（{a['code']}）━━")
        lines.append(a["note"])
        if a.get("decay", {}).get("pct") is not None:
            lines.append(f"· {a['decay']['text']}")
        lines.append("")
    lines.append("为什么单独提醒这条：")
    lines.append("公司里的人最了解自家情况，而 A股 这类公告最快 1 天就能看到 ——")
    lines.append("是所有信号里**唯一又快又可信**的一类。")
    lines.append("")
    lines.append("但它衰减也快：约一半的效果在头一个月内走完。")
    lines.append("所以值得现在看，不值得三个月后再翻出来当买入理由。")
    return title, "\n".join(lines)


def run(user_id: int = None, dry: bool = False) -> dict:
    """扫描 → 去重 → 推送。**推送成功才记账**（US-160 的教训：
    干跑不该吃掉条目，发送失败也不该把条目永久吞掉）。"""
    import db
    from radar_app.data.push_ledger import (commit_pushed, filter_changed,
                                            state_hash)

    alerts = find_alerts()
    if not alerts:
        return {"found": 0, "pushed": 0}

    if user_id is None:
        try:
            from scripts.stock_report import admin_user_id
            user_id = admin_user_id()
        except Exception:
            user_id = None
    if not user_id:
        return {"found": len(alerts), "pushed": 0, "error": "无收件人"}

    # 身份 = 这只股票的这一组 cluster；状态 = 人数+占比（追加买入会变）
    items = [(f"insider_cluster:{a['code']}:{a['cluster'].get('end','')}",
              state_hash(a["cluster"].get("n_insiders"),
                         a["cluster"].get("ratio_total")),
              a) for a in alerts]
    changed, _unchanged = filter_changed(user_id, items)
    fresh = [c[2] for c in changed]
    if not fresh:
        return {"found": len(alerts), "pushed": 0, "reason": "都推送过了"}

    title, body = build_message(fresh)
    if dry:
        return {"found": len(alerts), "pushed": 0, "dry": True,
                "title": title, "body": body}

    key = os.environ.get("SERVERCHAN_KEY")
    if not key:
        return {"found": len(alerts), "pushed": 0, "error": "无 SERVERCHAN_KEY"}
    from scripts.stock_pipeline import send_serverchan
    send_serverchan(key, title, body)
    commit_pushed(user_id, changed)
    return {"found": len(alerts), "pushed": len(fresh),
            "codes": [a["code"] for a in fresh]}


if __name__ == "__main__":
    import db
    db.init_db()
    r = run(dry=True)
    print({k: v for k, v in r.items() if k != "body"})
    if r.get("body"):
        print("\n" + r["body"])
