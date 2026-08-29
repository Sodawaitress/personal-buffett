"""US-203：给美股补市盈率历史分位。

US-202 量出来生产上 38 只美股**没有一只**有估值分位，于是估值档只能靠
股价位置，而股价位置说不了贵贱 —— 修完之后它们集体是「估值数据不足」。
诚实，但没用。

这个脚本用 yfinance 的年度 EPS + 周线价格算出分位，**并把窗口长度一起存**
（美股实际 3.5-4 年，不是列名暗示的 5 年）。

算不出来的照样留空：亏损或刚扭亏的公司（INTC、ETSY、多邻国）
正利润历史不足 3 年，**「没有可比历史」是正确答案，不是缺陷**。
"""
import json
import sys

from radar_app.data.core import get_engine
from sqlalchemy import text

from scripts.us_valuation_percentile import pe_percentile, describe


def _needs_percentile(code: str) -> bool:
    """A 股以外的都算 —— 名字别再叫 `_is_us`。

    第一版叫 `_is_us`，判据是「不是 6 位数字」，于是 2359.HK / XRO.NZ
    也被放了进来。它们**确实**该被处理（港股纽股同样没有分位，
    yfinance 也同样能拉），但函数名说的是另一回事。
    名字和判据不一致，下一个人（包括我自己）就会照名字去理解代码。
    """
    return bool(code) and not code.isdigit()


def run(limit: int = 40) -> dict:
    import yfinance as yf
    from scripts.normalized_earnings import normalize

    # US-203：脚本直连数据库，**不经过 Flask 启动流程**，所以迁移不会自动跑。
    # 第一次上生产时 pe_pct_window_years 列不存在，12 只算出分位的股票
    # 全部写入失败 —— 而日志里只报 UndefinedColumn，看着像权限问题。
    # 和 scripts/industry_benchmarks.py 同一个模式：自己先确保列在。
    from radar_app.data import core as _db
    _db._migrate()

    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT code, annual_json, pe_current, pe_percentile_5y "
            "FROM stock_fundamentals")).mappings().all()

    todo = [r for r in rows if _needs_percentile(r["code"]) and r["pe_percentile_5y"] is None]
    stat = {"done": 0, "no_history": 0, "failed": 0, "total": len(todo)}

    for r in todo[:limit]:
        code = r["code"]
        try:
            # 被一次性收益抬高的那年要先还原，否则历史 PE 假性偏低
            try:
                ann = json.loads(r["annual_json"] or "[]")
            except Exception:
                ann = []
            norm = normalize(ann, market="us")
            ratio = None
            if norm and norm.get("reported"):
                ratio = norm["normalized"] / norm["reported"]

            res = pe_percentile(yf.Ticker(code), r["pe_current"],
                                normalized_eps_ratio=ratio)
            if not res:
                stat["no_history"] += 1
                print(f"  ⏭ {code}  {describe(res)}")
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE stock_fundamentals SET pe_percentile_5y=:p, "
                    "pe_pct_window_years=:y, pe_pct_range=:r WHERE code=:c"),
                    {"p": res["pct"], "y": res["years"],
                     "r": f"{res['low']}-{res['high']}", "c": code})
            stat["done"] += 1
            print(f"  ✅ {code}  {describe(res)}")
        except Exception as e:
            stat["failed"] += 1
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    stat["remaining"] = max(0, stat["total"] - limit)
    return stat


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
    print(run(lim))
