"""五选台账：推荐当天落账，5/10/20 日由代码自动回填（US-192）。

## 为什么要有它

用户要看五选的准确度，结果**调不出来** —— `picks_open.json` 只记
「推荐了什么」，不记后来怎么样；历史五选散落在推送正文里，
算一次要靠 git 考古（US-189）。

而算出来那次（35 条、胜率 68.6%、平均 +1.2%）有三个致命缺陷：
**没有基准**（同期大盘 +4%，实际跑输）、**持有期不齐**（早推荐的占便宜）、
**样本高度重复**（35 条只覆盖约 15 只）。

## 关键设计：Claude 写不了自己的成绩单

五选是 **Claude 在每日 routine 里人工判断**选出来的（不是算法）。
所以 US-189 那次评估是「我给我自己打分」，有结构性的利益冲突。

    Claude（routine）  →  只写 picks_open.json（推荐了什么）
    流水线（纯代码）    →  落账 + 回填收益 + 算超额        ← Claude 碰不到

三个月后拿到的是**一张改不了的成绩单**。

## 基准怎么来

没有指数数据：`market_data.cn_indices` 只存最新快照、无历史且停在 07-28；
东财 K 线接口 `push2delay` / `push2his` 两台都返回空。

所以用**自选池当日等权平均涨跌**当基准（实测 8 月 19 个交易日、
每天 210–244 只，样本足够）。而且对这个场景**更贴切** ——
用户关心的不是「跑赢上证」，是「**这五只比我池子里其余的强吗**」。

## 为什么用交易日而不是自然日

「5 日」必须是 5 个**有价格的交易日**。用自然日会把周末算进去，
不同推荐日的持有期就不可比 —— 那正是 US-189 那次评估的缺陷之一。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HORIZONS = (5, 10, 20)


def _conn():
    from radar_app.data.core import get_conn
    return get_conn()


def ingest(path: str = "output/picks_open.json") -> dict:
    """把 Claude 写的 picks_open.json 落成台账行。

    **只增不改**：同一 (code, pick_date) 已存在就跳过 ——
    落账价一旦锁定就不能再动，否则成绩单可以被事后修饰。
    """
    try:
        picks = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"read": 0, "added": 0, "skipped": 0, "error": "读不到 picks_open.json"}
    if not isinstance(picks, list):
        return {"read": 0, "added": 0, "skipped": 0, "error": "格式不是数组"}

    added = skipped = 0
    with _conn() as c:
        for p in picks:
            code = str(p.get("code") or "").strip()
            d = str(p.get("date") or "")[:10]
            if not code or len(d) != 10:
                continue
            exists = c.execute(
                "SELECT 1 FROM pick_ledger WHERE code=:c AND pick_date=:d",
                {"c": code, "d": d}).fetchone()
            if exists:
                skipped += 1
                continue
            sig = p.get("signals") or {}
            # 落账价优先用推荐当天快照里的价；没有就留空，回填时再找
            entry = sig.get("price")
            c.execute("""
                INSERT INTO pick_ledger
                  (code, name, pick_date, entry_price, grade, quant_score,
                   advice, reason_tags, updated_at)
                VALUES (:c,:n,:d,:e,:g,:q,:a,:t,CURRENT_TIMESTAMP)
            """, {"c": code, "n": p.get("name"), "d": d, "e": entry,
                  "g": sig.get("grade"), "q": sig.get("quant_score"),
                  "a": (p.get("advice") or "")[:500],
                  "t": json.dumps(_tag_reasons(p), ensure_ascii=False)})
            added += 1
    return {"read": len(picks), "added": added, "skipped": skipped}


# 推荐理由分类。**这是台账最有价值的一列** —— 三个月后能回答
# 「我哪一类理由准」，某类长期不准就该从五选依据里拿掉。
_REASON_PATTERNS = {
    "机构调研":   ("调研", "专程研究", "机构在看"),
    "资金流入":   ("主力", "资金流入", "净流入"),
    "融券变化":   ("融券", "空头"),
    "内部人":     ("内部人", "高管", "增持", "减持"),
    "估值":       ("估值", "便宜", "市盈", "低位"),
    "业绩":       ("业绩", "营收", "利润", "订单", "合同负债"),
    "技术形态":   ("突破", "均线", "回调", "支撑"),
    "行业":       ("行业", "板块", "赛道"),
}


def _tag_reasons(pick: dict) -> list:
    """从 advice 正文里抽理由标签。抽不到返回 [] —— 不硬塞。"""
    text = str(pick.get("advice") or "")
    return [tag for tag, kws in _REASON_PATTERNS.items()
            if any(k in text for k in kws)]


# US-189 从 git 里逐日抠出来的历史五选。台账是 2026-08-28 才建的，
# 不灌这批的话要等三周才有第一份成绩单。
# **只灌一次**（靠 UNIQUE(code, pick_date) 兜底），且不含 advice ——
# 历史推荐的理由分类抠不出来，硬编只会造出假标签。
_HISTORICAL = {
    "2026-08-11": ["689009", "300124", "688008", "300394", "000333"],
    "2026-08-18": ["300394", "300124", "301349", "002415", "002142"],
    "2026-08-19": ["300684", "000333", "002415", "600415", "000001"],
    "2026-08-20": ["300476", "300394", "000333", "002415", "000001"],
    "2026-08-21": ["300394", "000680", "002142", "000333", "002252"],
}


def seed_history() -> dict:
    """一次性灌入 US-189 抠出的历史推荐。重复运行安全（已存在则跳过）。"""
    added = skipped = 0
    with _conn() as c:
        for d, codes in sorted(_HISTORICAL.items()):
            for code in codes:
                if c.execute("SELECT 1 FROM pick_ledger WHERE code=:c AND pick_date=:d",
                             {"c": code, "d": d}).fetchone():
                    skipped += 1
                    continue
                nm = c.execute("SELECT COALESCE(name_cn,name) AS n FROM stocks WHERE code=:c",
                               {"c": code}).fetchone()
                c.execute("""
                    INSERT INTO pick_ledger (code, name, pick_date, reason_tags, updated_at)
                    VALUES (:c, :n, :d, '[]', CURRENT_TIMESTAMP)
                """, {"c": code, "n": (nm["n"] if nm else None), "d": d})
                added += 1
    return {"added": added, "skipped": skipped}


def _trading_days_after(c, code: str, d0: str, n: int):
    """从 d0 之后第 n 个**有价格的交易日**的价格。不足 n 天返回 None。"""
    rows = c.execute("""
        SELECT DISTINCT substr(fetched_at,1,10) AS d, price
        FROM stock_prices
        WHERE code=:c AND fetched_at > :d0 AND price IS NOT NULL
        ORDER BY d ASC LIMIT :n
    """, {"c": code, "d0": d0 + " 23:59:59", "n": n}).fetchall()
    if len(rows) < n:
        return None, None
    return rows[-1]["price"], rows[-1]["d"]


def _bench_between(c, d0: str, d1: str):
    """两个日期之间，自选池的等权平均累计涨跌（%）。

    逐日 AVG(change_pct) 再累加 —— 不是「首尾价格比」，
    因为池子里每天有价的股票不完全相同，首尾比会失真。
    """
    rows = c.execute("""
        SELECT substr(fetched_at,1,10) AS d, AVG(change_pct) AS a
        FROM stock_prices
        WHERE change_pct IS NOT NULL
          AND substr(fetched_at,1,10) > :d0 AND substr(fetched_at,1,10) <= :d1
        GROUP BY 1 HAVING COUNT(DISTINCT code) >= 30
    """, {"d0": d0, "d1": d1}).fetchall()
    if not rows:
        return None
    return round(sum(float(r["a"] or 0) for r in rows), 2)


def backfill() -> dict:
    """回填收益。**纯代码，Claude 无权参与。**"""
    done = {h: 0 for h in HORIZONS}
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM pick_ledger WHERE resolved_20d = 0").fetchall()
        for r in rows:
            code, d0 = r["code"], r["pick_date"]
            entry = r["entry_price"]
            if not entry:
                # 落账时没记价 —— 用推荐日当天/之后第一个价补上，但只补一次
                p = c.execute("""
                    SELECT price FROM stock_prices WHERE code=:c
                      AND fetched_at >= :d AND price IS NOT NULL
                      ORDER BY fetched_at ASC LIMIT 1
                """, {"c": code, "d": d0}).fetchone()
                entry = p["price"] if p else None
                if entry:
                    c.execute("UPDATE pick_ledger SET entry_price=:e WHERE id=:i",
                              {"e": entry, "i": r["id"]})
            if not entry or entry <= 0:
                continue

            upd, all_done = {}, True
            for h in HORIZONS:
                if r[f"ret_{h}d"] is not None:
                    continue
                px, d1 = _trading_days_after(c, code, d0, h)
                if px is None:
                    all_done = False
                    continue
                ret = round((px - entry) / entry * 100, 2)
                bench = _bench_between(c, d0, d1)
                upd[f"ret_{h}d"] = ret
                if bench is not None:
                    upd[f"bench_{h}d"] = bench
                    upd[f"excess_{h}d"] = round(ret - bench, 2)
                done[h] += 1
            if upd:
                sets = ", ".join(f"{k}=:{k}" for k in upd)
                params = {**upd, "i": r["id"]}
                c.execute(f"UPDATE pick_ledger SET {sets}, "
                          f"updated_at=CURRENT_TIMESTAMP WHERE id=:i", params)
            if all_done and r["ret_20d"] is None and upd.get("ret_20d") is None:
                all_done = False
            if all_done:
                c.execute("UPDATE pick_ledger SET resolved_20d=1 WHERE id=:i",
                          {"i": r["id"]})
    return {"filled_5d": done[5], "filled_10d": done[10], "filled_20d": done[20]}


def scorecard(horizon: int = 10) -> dict:
    """成绩单。报**超额收益**，不报绝对胜率 ——
    没有基准的胜率会误导（US-189：绝对 +1.2% 其实跑输大盘 +4%）。"""
    col, ecol = f"ret_{horizon}d", f"excess_{horizon}d"
    with _conn() as c:
        rows = c.execute(
            f"SELECT code, name, pick_date, {col} AS r, {ecol} AS e, reason_tags "
            f"FROM pick_ledger WHERE {col} IS NOT NULL").fetchall()
    if not rows:
        # 早返回也要带齐字段 —— 否则调用方/模板会 KeyError。
        # 本仓栽过一次（US-177 内部人卡片的空数据分支）。
        return {"horizon": horizon, "n": 0, "n_with_bench": 0,
                "beat_bench": 0, "avg_excess": None, "by_reason": {}}
    ex = [float(r["e"]) for r in rows if r["e"] is not None]
    by_tag = {}
    for r in rows:
        if r["e"] is None:
            continue
        try:
            tags = json.loads(r["reason_tags"] or "[]")
        except Exception:
            tags = []
        for t in tags or ["（无标签）"]:
            by_tag.setdefault(t, []).append(float(r["e"]))
    return {
        "horizon": horizon,
        "n": len(rows),
        "n_with_bench": len(ex),
        "beat_bench": sum(1 for x in ex if x > 0),
        "avg_excess": round(sum(ex) / len(ex), 2) if ex else None,
        "by_reason": {t: {"n": len(v), "avg_excess": round(sum(v) / len(v), 2)}
                      for t, v in sorted(by_tag.items(),
                                         key=lambda kv: -len(kv[1]))},
    }


if __name__ == "__main__":
    import db
    db.init_db()
    print("历史灌入:", seed_history())
    print("落账:", ingest())
    print("回填:", backfill())
    for h in HORIZONS:
        print(f"成绩单 {h}日:", scorecard(h))
