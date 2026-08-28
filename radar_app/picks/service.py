"""今日五选页的数据组装（US-196/197）。

## 核心：每条推荐都带着它的历史战绩出现

用户要的「验证对不对」是这个意思 —— 不是「验证 routine 跑了没」，
是**把台账的结果标回五选页**：

    澜起科技 (688008)  +10.06%
    ⟵ 这只股票被推荐过 2 次，平均跑赢大盘 +1.2%

**每条推荐旁边就是它上次的成绩。** 如果某只反复被选中却反复跑输，
一眼就看得出来 —— 这是让判断力接受检验的最直接方式。

结果全部来自 `pick_ledger`，由流水线自动回填（US-192），Claude 碰不到。
"""


def build(path: str = "output/daily_push.txt") -> dict:
    from radar_app.picks.parser import parse_file
    doc = parse_file(path)
    if not doc:
        return {}

    # 每条挂上台账战绩 + 是否在自选里
    try:
        from scripts.pick_ledger import history_for
    except Exception:
        history_for = None

    for it in doc["items"]:
        it["history"] = (history_for(it["code"]) or {}) if history_for else {}

    # 整组的行业集中度（US-193）—— 「名字不同 ≠ 篮子不同」
    try:
        from scripts.pick_ledger import concentration
        doc["concentration"] = concentration(doc["date"]) or {}
    except Exception:
        doc["concentration"] = {}

    # 新鲜度：五选是哪天的，离今天多久
    try:
        from datetime import date as _d
        doc["age_days"] = (_d.today() - _d.fromisoformat(doc["date"])).days
    except Exception:
        doc["age_days"] = None
    return doc


def archive(limit: int = 40) -> list:
    """历史五选（从台账来，不依赖推送正文 —— 那个每天被覆盖）。"""
    from radar_app.data.core import get_conn
    with get_conn() as c:
        rows = c.execute("""
            SELECT pick_date, COUNT(*) AS n,
                   AVG(excess_10d) AS ex10, AVG(excess_5d) AS ex5
            FROM pick_ledger GROUP BY pick_date ORDER BY pick_date DESC LIMIT :n
        """, {"n": limit}).fetchall()
    out = []
    for r in rows:
        ex = r["ex10"] if r["ex10"] is not None else r["ex5"]
        out.append({
            "date": r["pick_date"], "n": r["n"],
            "excess": round(float(ex), 2) if ex is not None else None,
            "horizon": 10 if r["ex10"] is not None else (5 if r["ex5"] is not None else None),
        })
    return out
