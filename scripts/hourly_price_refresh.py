"""临时验证/轻量刷新：只拉 A股价格入库 + 报新鲜度。无 LLM、无推送。
用于每小时观察 yfinance 兜底是否稳定刷新 A股价格。稳定后可删。"""
from datetime import datetime

import db as _db
from radar_app.data.core import get_conn
from scripts.stock_fetch import fetch_quotes


def main():
    with get_conn() as c:
        rows = c.execute(
            "SELECT DISTINCT w.stock_code, COALESCE(s.name_cn, s.name, w.stock_code) nm "
            "FROM user_watchlist w LEFT JOIN stocks s ON s.code = w.stock_code "
            "WHERE w.status != 'sold' AND s.market = 'cn'"
        ).fetchall()
    cn = [(r["nm"], r["stock_code"]) for r in rows]
    print(f"拉取 {len(cn)} 只 A股行情...")
    quotes = fetch_quotes(cn)
    date_str = datetime.now().strftime("%Y-%m-%d")
    n = 0
    for code, q in quotes.items():
        try:
            _db.upsert_quote(code, date_str, q["price"], q["change"], q["amount"])
            n += 1
        except Exception as e:
            print(f"  upsert {code} failed: {e}")
    print(f"✅ 已更新 {n}/{len(cn)} 只 A股价格")
    with get_conn() as c:
        r = dict(c.execute(
            "SELECT MAX(p.fetched_at) m, COUNT(DISTINCT p.code) n FROM stock_prices p "
            "JOIN stocks s ON s.code = p.code WHERE s.market = 'cn'"
        ).fetchone())
    print(f"📊 A股价格库最新: {r['m']} ({r['n']} 只)")


if __name__ == "__main__":
    main()
