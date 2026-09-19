"""US-216：补海外收入占比。

数据源东财主营构成按地区（`stock_zygc_em`）。实测 10 只覆盖 8 只 ——
**拿不到就留空，不猜**。这正是本条 US 的起点：我猜过一次，猜错了。
"""
import sys

from sqlalchemy import text

from radar_app.data.core import get_engine
from scripts.overseas_exposure import compute


def run(limit: int = 40, refresh: bool = False) -> dict:
    import akshare as ak

    from radar_app.data import core as _db
    _db._migrate()
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT code, overseas_pct FROM stock_fundamentals")).mappings().all()

    todo = [r["code"] for r in rows
            if r["code"] and r["code"].isdigit() and len(r["code"]) == 6
            and (refresh or r["overseas_pct"] is None)]
    stat = {"done": 0, "no_data": 0, "failed": 0, "total": len(todo)}

    for code in todo[:limit]:
        try:
            sym = ("SH" if code[0] in "056" else "SZ") + code
            r = compute(ak.stock_zygc_em(symbol=sym))
            if not r:
                stat["no_data"] += 1
                print(f"  ⏭ {code}  没有地区拆分，留空")
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE stock_fundamentals SET overseas_pct=:p, "
                    "overseas_asof=:a WHERE code=:c"),
                    {"p": r["pct"], "a": r["asof"], "c": code})
            stat["done"] += 1
            print(f"  ✅ {code}  海外 {r['pct']}%  （{r['asof']}）")
        except Exception as e:
            stat["failed"] += 1
            print(f"  ❌ {code}: {type(e).__name__}")

    stat["remaining"] = max(0, stat["total"] - limit)
    return stat


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [a for a in args if a.isdigit()]
    print(run(int(nums[0]) if nums else 40, refresh="--refresh" in args))
