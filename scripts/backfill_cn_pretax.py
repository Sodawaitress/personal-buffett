"""US-205：给 A 股补税前利润 / 所得税字段。

US-202 把「利润总额」写进了 `fetch_cn_advanced`，但那一步在日常抓取里
**每轮只跑 2 只**（它要打 3 个新浪报表接口，很重）。222 只 A 股轮一遍
要一百多天 —— 等于没做。

这和 US-202 开篇那条是同一句话：**需要慢慢等才生效的东西，等于没做。**
所以照美股 `backfill_us_pe_percentile` 的样子补一个，挂进同一个
backfill-svc，每轮限量跑，几天补完。

补上之后，US-172 的一次性收益检查（净利润 > 税前利润）才第一次
对 A 股生效 —— 在此之前生产上 222 只 A 股有税前利润字段的是 **0 只**。
"""
import json
import sys

from sqlalchemy import text

from radar_app.data.core import get_engine


def _is_ashare(code: str) -> bool:
    return bool(code) and code.isdigit() and len(code) == 6


def run(limit: int = 30, refresh: bool = False) -> dict:
    from scripts.stock_fetch import fetch_cn_advanced

    from radar_app.data import core as _db
    _db._migrate()

    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT code, annual_json FROM stock_fundamentals")).mappings().all()

    todo = []
    for r in rows:
        if not _is_ashare(r["code"]):
            continue
        try:
            ann = json.loads(r["annual_json"] or "[]")
        except Exception:
            ann = []
        if not ann:
            continue
        if refresh or ann[0].get("pretax_income") is None:
            todo.append((r["code"], ann))

    stat = {"done": 0, "no_data": 0, "failed": 0, "total": len(todo)}
    for code, ann in todo[:limit]:
        try:
            fetch_cn_advanced(code, annual=ann)      # 原地写进 ann
            if ann[0].get("pretax_income") is None:
                stat["no_data"] += 1
                print(f"  ⏭ {code}  利润表里没有「利润总额」")
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE stock_fundamentals SET annual_json=:j WHERE code=:c"),
                    {"j": json.dumps(ann, ensure_ascii=False), "c": code})
            stat["done"] += 1
            print(f"  ✅ {code}  税前 {ann[0].get('pretax_income')} / "
                  f"净利 {ann[0].get('net_profit')}")
        except Exception as e:
            stat["failed"] += 1
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    stat["remaining"] = max(0, stat["total"] - limit)
    return stat


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [a for a in args if a.isdigit()]
    print(run(int(nums[0]) if nums else 30, refresh="--refresh" in args))
