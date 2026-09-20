"""US-216：补海外收入占比。

数据源东财主营构成按地区（`stock_zygc_em`）。实测 10 只覆盖 8 只 ——
**拿不到就留空，不猜**。这正是本条 US 的起点：我猜过一次，猜错了。
"""
import sys

from sqlalchemy import text

from radar_app.data.core import get_engine
from scripts.overseas_exposure import compute, finance_swing


def _fx_change():
    """同口径的人民币变动：本期平均 vs 上期平均。

    **营收换算要用期间平均，不是两个时点的即期汇率。**
    实测 2025H1 平均 724.32 → 2026H1 平均 685.44，人民币升值 5.4%。
    """
    try:
        import datetime as dt

        import akshare as ak
        df = ak.currency_boc_sina(symbol="美元", start_date="20250101",
                                  end_date=dt.date.today().strftime("%Y%m%d"))
        s = df.dropna(subset=["中行汇买价"]).set_index("日期")["中行汇买价"]
        y = dt.date.today().year

        def avg(y0, m0, y1, m1):
            a = [v for d, v in s.items() if dt.date(y0, m0, 1) <= d < dt.date(y1, m1, 1)]
            return sum(a) / len(a) if a else None
        cur, prev = avg(y, 1, y, 7), avg(y - 1, 1, y - 1, 7)
        return round((1 - cur / prev) * 100, 1) if cur and prev else None
    except Exception:
        return None


def _fx_pending():
    """本期至今 vs 去年同一段日历窗口。

    **必须对齐同一段日历窗口** —— 拿「今年 7-9 月」去比「去年 7-12 月」，
    会把季节性当成汇率变动。本仓那族错误的又一个版本。
    """
    try:
        import datetime as dt

        import akshare as ak
        today = dt.date.today()
        df = ak.currency_boc_sina(symbol="美元", start_date="20250101",
                                  end_date=today.strftime("%Y%m%d"))
        s = df.dropna(subset=["中行汇买价"]).set_index("日期")["中行汇买价"]
        m0 = 7 if today.month >= 7 else 1          # 本报告期起点
        y = today.year

        def avg(yy):
            a = [v for d, v in s.items()
                 if dt.date(yy, m0, 1) <= d <= today.replace(year=yy)]
            return sum(a) / len(a) if a else None
        cur, prev = avg(y), avg(y - 1)
        if not cur or not prev:
            return None, None
        label = ("年报明年 4 月才披露" if m0 == 7 else "中报今年 8 月才披露")
        return round((1 - cur / prev) * 100, 1), label
    except Exception:
        return None, None


def run(limit: int = 40, refresh: bool = False) -> dict:
    import akshare as ak

    from radar_app.data import core as _db
    _db._migrate()
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT code, overseas_pct FROM stock_fundamentals")).mappings().all()

    fx = _fx_change()          # 市场级，一次算好给所有股票用
    fx_pend, _ = _fx_pending()
    todo = [r["code"] for r in rows
            if r["code"] and r["code"].isdigit() and len(r["code"]) == 6
            and (refresh or r["overseas_pct"] is None)]
    stat = {"done": 0, "no_data": 0, "failed": 0, "total": len(todo)}

    for code in todo[:limit]:
        try:
            sym = ("SH" if code[0] in "056" else "SZ") + code
            r = compute(ak.stock_zygc_em(symbol=sym))
            _pf = ak.stock_profit_sheet_by_report_em(symbol=sym)
            sw = finance_swing(_pf)
            rev_yoy = None
            try:
                _c = _pf.iloc[0]
                import math as _m
                _v = float(_c["TOTAL_OPERATE_INCOME_YOY"])
                rev_yoy = None if _m.isnan(_v) else round(_v, 1)
            except Exception:
                rev_yoy = None
            if not r and not sw:
                stat["no_data"] += 1
                print(f"  ⏭ {code}  地区拆分和财务费用都拿不到，留空")
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE stock_fundamentals SET overseas_pct=:p, overseas_asof=:a, "
                    "fin_exp_cur=:fc, fin_exp_prev=:fp, fin_exp_rev_pct=:fr, "
                    "fin_exp_asof=:fa, fin_exp_kind=:fk, fx_change_pct=:fx, rev_yoy=:ry WHERE code=:c"),
                    {"p": (r or {}).get("pct"), "a": (r or {}).get("asof"),
                     "fc": (sw or {}).get("cur"), "fp": (sw or {}).get("prev"),
                     "fr": (sw or {}).get("delta_rev_pct"),
                     "fa": (sw or {}).get("asof"), "fk": (sw or {}).get("kind"),
                     "fx": fx, "ry": rev_yoy, "fxp": fx_pend, "c": code})
            stat["done"] += 1
            print(f"  ✅ {code}  海外 {(r or {}).get('pct')}%  "
                  f"财务费用增量/营收 {(sw or {}).get('delta_rev_pct')}%")
        except Exception as e:
            stat["failed"] += 1
            print(f"  ❌ {code}: {type(e).__name__}")

    stat["remaining"] = max(0, stat["total"] - limit)
    return stat


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [a for a in args if a.isdigit()]
    print(run(int(nums[0]) if nums else 40, refresh="--refresh" in args))
