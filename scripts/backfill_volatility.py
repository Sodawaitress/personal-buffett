"""US-208：给每只股票算「颠不颠」并存起来。

页面上现算不行 —— 要 500 天日线。照 US-203 的模式：补数存字段，页面只读。

**基准必须同市场。** 拿沪深300 去比美股，倍数没有意义
（US-202 那一整族错误：跨语境套用）。
"""
import json as _json
import sys

from sqlalchemy import text

from radar_app.data.core import get_engine
from scripts.volatility_profile import BENCHMARK, profile, volatility

_DAYS = 500          # 约两年。一年只有 51 个周收益，不够判「脾气稳不稳」


def _market(code: str) -> str:
    if code.isdigit() and len(code) == 6:
        return "cn"
    if code.endswith(".HK"):
        return "hk"
    if code.endswith(".NZ"):
        return "nz"
    return "us"


def _closes(code: str, market: str):
    if market == "cn":
        import akshare as ak
        pre = "sh" if code[0] in "056" else "sz"
        df = ak.stock_zh_a_daily(symbol=pre + code, adjust="qfq")
        return list(df["close"].astype(float))[-_DAYS:]
    import yfinance as yf
    h = yf.Ticker(code).history(period="2y")
    return list(h["Close"].astype(float))[-_DAYS:] if h is not None and len(h) else []


def _bench(market: str):
    sym = BENCHMARK[market][0]
    if market == "cn":
        import akshare as ak
        return list(ak.stock_zh_index_daily(symbol=sym)["close"].astype(float))[-_DAYS:]
    import yfinance as yf
    h = yf.Ticker(sym).history(period="2y")
    return list(h["Close"].astype(float))[-_DAYS:] if h is not None and len(h) else []


def run(limit: int = 40, refresh: bool = False) -> dict:
    from radar_app.data import core as _db
    _db._migrate()
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT code, vol_weekly FROM stock_fundamentals")).mappings().all()

    todo = [r["code"] for r in rows if refresh or r["vol_weekly"] is None]
    stat = {"done": 0, "no_data": 0, "failed": 0, "total": len(todo)}

    bench_cache, peer_vols = {}, {}
    batch = todo[:limit]
    computed = {}
    for code in batch:
        mkt = _market(code)
        try:
            if mkt not in bench_cache:
                bench_cache[mkt] = _bench(mkt)
            _cl = _closes(code, mkt)
            v = profile(_cl, bench_cache[mkt], mkt)
            if v:
                from scripts.volatility_profile import weekly_returns
                v["_series"] = [round(x, 5) for x in weekly_returns(_cl)]
            if not v:
                stat["no_data"] += 1
                print(f"  ⏭ {code}  历史不够，算不出波动")
                continue
            computed[code] = v
            peer_vols.setdefault(mkt, []).append(v["vol"])
        except Exception as e:
            stat["failed"] += 1
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    # 分位要等同市场的同伴都算完才有意义 —— 所以放在第二轮
    for code, v in computed.items():
        mkt = _market(code)
        pool = peer_vols.get(mkt) or []
        pct = (round(sum(1 for x in pool if x <= v["vol"]) / len(pool) * 100)
               if len(pool) >= 5 else None)      # 样本太小的分位没有意义
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE stock_fundamentals SET vol_weekly=:v, vol_ratio=:r, "
                "vol_pct=:p, vol_stable=:s, vol_series=:q WHERE code=:c"),
                {"v": v["vol"], "r": v["ratio"], "p": pct,
                 "q": _json.dumps(v.get("_series") or []),
                 "s": None if v["stable"] is None else int(v["stable"]),
                 "c": code})
        stat["done"] += 1
        print(f"  ✅ {code}  周波动 {v['vol']}%  {v['ratio']}× {v['bench_name']}"
              f"  稳定={v['stable']}  分位={pct}")

    stat["remaining"] = max(0, stat["total"] - limit)
    return stat


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [a for a in args if a.isdigit()]
    print(run(int(nums[0]) if nums else 40, refresh="--refresh" in args))
