"""US-172：给已有的美股年报补上 pretax_income / tax_provision。

新字段是 2026-08-25 才加进 pipeline_fetch 的，之前抓的记录都没有，
所以「还原真实市盈率」在补数之前是**完全不生效**的（normalize 返回空，
页面照旧显示被做低的市盈率）。

只补这两个字段，**不动任何已有值** —— 本仓一贯做法：数据源怎么给就怎么存，
改写原始值会让以后对不上账。

用法：
    python -m scripts.backfill_tax_fields            # 全部美股
    python -m scripts.backfill_tax_fields DUOL NVDA  # 指定几只
"""
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from radar_app.data.core import get_conn  # noqa: E402


def _yi(v):
    try:
        f = float(v)
        return round(f / 1e8, 2) if f == f else None
    except (TypeError, ValueError):
        return None


def backfill(codes=None, sleep_s: float = 1.0) -> dict:
    import yfinance as yf

    with get_conn() as c:
        if codes:
            rows = [dict(r) for r in c.execute(
                "SELECT f.code, f.annual_json FROM stock_fundamentals f "
                "WHERE f.code IN :codes".replace(":codes", "(" + ",".join(
                    f"'{x}'" for x in codes) + ")"))]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT f.code, f.annual_json FROM stock_fundamentals f "
                "JOIN stocks s ON s.code = f.code WHERE s.market = 'us'")]

    done = skipped = failed = 0
    for r in rows:
        try:
            annual = json.loads(r["annual_json"] or "[]")
        except Exception:
            annual = []
        if not annual:
            skipped += 1
            continue
        if all(y.get("pretax_income") is not None for y in annual):
            skipped += 1          # 已经补过
            continue
        try:
            fin = yf.Ticker(r["code"]).financials
            by_year = {}
            for col in fin.columns:
                y = str(col.year) if hasattr(col, "year") else str(col)[:4]
                by_year[y] = (
                    _yi(fin.loc["Pretax Income", col]) if "Pretax Income" in fin.index else None,
                    _yi(fin.loc["Tax Provision", col]) if "Tax Provision" in fin.index else None,
                )
            hit = False
            for y in annual:
                pre, tax = by_year.get(str(y.get("year")), (None, None))
                if pre is not None:
                    y["pretax_income"] = pre
                    hit = True
                if tax is not None:
                    y["tax_provision"] = tax
            if not hit:
                failed += 1
                continue
            with get_conn() as c:
                c.execute("UPDATE stock_fundamentals SET annual_json=:a WHERE code=:c",
                          {"a": json.dumps(annual, ensure_ascii=False), "c": r["code"]})
            done += 1
            print(f"  ✅ {r['code']}")
        except Exception as e:
            failed += 1
            print(f"  ⚠️ {r['code']}: {type(e).__name__}: {str(e)[:60]}")
        time.sleep(sleep_s)
    return {"done": done, "skipped": skipped, "failed": failed, "total": len(rows)}


if __name__ == "__main__":
    print(backfill(sys.argv[1:] or None))
