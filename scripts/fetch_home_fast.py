"""
首页快速数据拉取：价格 + 主力资金流向（CN 股）。
不跑 LLM，不跑财务分析，只更新信号所需的实时数据。
耗时目标 < 60 秒。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
import requests

import db
from radar_app.data.core import get_conn

CN_TZ = timezone(timedelta(hours=8))


def _load_cn_codes() -> list[str]:
    with get_conn() as c:
        rows = c.execute(
            """SELECT DISTINCT w.stock_code FROM user_watchlist w
               JOIN stocks s ON s.code = w.stock_code
               WHERE s.market='cn' AND w.status IN ('holding','watching')"""
        ).fetchall()
    return [r["stock_code"] for r in rows]


def _fetch_prices(codes: list[str]):
    """Sina 行情一次性批量拉，比逐只快很多。"""
    pure_map = {}
    for code in codes:
        pure = code.split(".")[0]
        prefix = "sh" if pure.startswith(("5", "6", "9")) else "sz"
        pure_map[f"{prefix}{pure}"] = code

    batch = ",".join(pure_map.keys())
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={batch}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=15,
        )
        for line in r.text.strip().splitlines():
            if '="' not in line:
                continue
            key = line.split("=")[0].split("_")[-1].strip()
            code = pure_map.get(key)
            if not code:
                continue
            fields = line.split('"')[1].split(",")
            if len(fields) < 10:
                continue
            try:
                price = float(fields[3]) if fields[3] else 0.0
                prev  = float(fields[2]) if fields[2] else 0.0
                chg   = round((price - prev) / prev * 100, 2) if prev else None
                amt   = float(fields[9]) / 1e8 if fields[9] else None
                if price:
                    db.upsert_price(code, price, change_pct=chg, volume=amt)
                    print(f"  {code} ¥{price} ({chg:+.2f}%)" if chg else f"  {code} ¥{price}")
            except Exception:
                pass
    except Exception as e:
        print(f"  ⚠ 价格批量拉取失败: {e}")


def _fetch_fund_flow_one(code: str):
    try:
        import akshare as ak
        pure = code.split(".")[0]
        market_side = "sh" if pure.startswith(("6", "9")) else "sz"
        df = ak.stock_individual_fund_flow(stock=pure, market=market_side)
        if df is not None and not df.empty:
            row = df.iloc[-1]
            date  = str(row.get("日期", datetime.now(CN_TZ).strftime("%Y-%m-%d")))[:10]
            net   = float(row.get("主力净流入-净额", 0)) / 1e8
            ratio = float(row.get("主力净流入-净占比", 0))
            db.upsert_fund_flow(code, date, net, ratio)
            print(f"  {code} 主力 {net:+.2f}亿 ({ratio:+.1f}%)")
    except Exception as e:
        print(f"  ⚠ {code} 资金流向失败: {e}")


def main():
    codes = _load_cn_codes()
    if not codes:
        print("没有 A 股自选股，跳过。")
        return

    print(f"快速更新 {len(codes)} 只 A 股价格…")
    _fetch_prices(codes)

    print(f"更新主力资金流向…")
    for code in codes:
        _fetch_fund_flow_one(code)

    print("完成。")


if __name__ == "__main__":
    main()
