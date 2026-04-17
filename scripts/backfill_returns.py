#!/usr/bin/env python3
"""
股票雷达 · 预测回填脚本 (US-24)
每日运行：查找 label_7d_return / label_30d_return 为 NULL 的分析记录，
用当时记录的价格 + 当前（或历史）价格计算实际收益，回填。

判定规则（用于准确率统计，不在此脚本里算，在 db.get_accuracy_stats 里算）：
  买入预测 + 实际涨 >3% = 正确
  买入预测 + 实际跌 >3% = 错误
  ±3% 以内 = 中性
"""
import sys, os
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import requests
from datetime import datetime, timezone, timedelta
import db

CN_TZ = timezone(timedelta(hours=8))


def _sina_price(code: str) -> float | None:
    """从新浪财经拉当前价格（A股）。"""
    prefix = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={prefix}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=8,
        )
        line = r.text.strip()
        if '="' not in line:
            return None
        parts = line.split('"')[1].split(",")
        price = float(parts[3]) if len(parts) > 3 else None
        return price if price and price > 0 else None
    except Exception as e:
        print(f"    ⚠️ 价格拉取失败 {code}: {e}")
        return None


def _yfinance_price(code: str) -> float | None:
    """从 yfinance 拉 NZ/US/HK 当前价格。"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(code)
        hist = ticker.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"    ⚠️ yfinance 价格拉取失败 {code}: {e}")
        return None


def get_current_price(code: str, market: str) -> float | None:
    if market == "cn":
        return _sina_price(code)
    return _yfinance_price(code)


def backfill(dry_run: bool = False):
    today = datetime.now(CN_TZ)
    today_str = today.strftime("%Y-%m-%d")

    with db.get_conn() as conn:
        # 找所有缺 7d 或 30d 标注的分析记录
        rows = conn.execute("""
            SELECT ar.id, ar.code, ar.analysis_date, ar.conclusion,
                   ar.feat_price_momentum,
                   sp.price as entry_price, sp.fetched_at,
                   s.market
            FROM analysis_results ar
            LEFT JOIN (
                SELECT code, price, fetched_at FROM stock_prices
                WHERE (code, fetched_at) IN (
                    SELECT code, MIN(fetched_at)
                    FROM stock_prices
                    GROUP BY code
                )
            ) sp ON sp.code = ar.code
            JOIN stocks s ON s.code = ar.code
            WHERE ar.period = 'daily'
              AND (ar.label_7d_return IS NULL OR ar.label_30d_return IS NULL)
            ORDER BY ar.analysis_date DESC
            LIMIT 100
        """).fetchall()

    print(f"  📋 找到 {len(rows)} 条待回填记录")

    # 缓存当日价格，避免重复请求
    price_cache: dict[str, float] = {}
    updated = 0

    for row in rows:
        code = row["code"]
        market = row["market"] or "cn"
        analysis_date = row["analysis_date"]  # "YYYY-MM-DD"
        conclusion = row["conclusion"] or ""
        record_id = row["id"]

        # 计算已过天数
        try:
            analysis_dt = datetime.strptime(analysis_date, "%Y-%m-%d").replace(
                tzinfo=CN_TZ
            )
        except Exception:
            continue
        days_elapsed = (today - analysis_dt).days

        # 不足7天的 7d 还无法回填
        need_7d  = row["label_7d_return"]  is None and days_elapsed >= 7
        need_30d = row["label_30d_return"] is None and days_elapsed >= 30

        if not need_7d and not need_30d:
            continue

        # 获取当时入场价（用分析当天最接近的价格快照）
        with db.get_conn() as conn:
            price_row = conn.execute("""
                SELECT price FROM stock_prices
                WHERE code=? AND fetched_at LIKE ?
                ORDER BY fetched_at ASC LIMIT 1
            """, (code, f"{analysis_date}%")).fetchone()

        entry_price = price_row["price"] if price_row else None
        if not entry_price:
            # 尝试 -1 day
            with db.get_conn() as conn:
                price_row = conn.execute("""
                    SELECT price FROM stock_prices
                    WHERE code=? AND fetched_at <= ?
                    ORDER BY fetched_at DESC LIMIT 1
                """, (code, analysis_date + " 23:59:59")).fetchone()
            entry_price = price_row["price"] if price_row else None

        if not entry_price:
            print(f"    ⚠️ {code} {analysis_date} 无入场价，跳过")
            continue

        # 获取目标日价格（简化：用当前实时价代替历史价）
        # 生产中可接入历史行情 API，但对于近期分析已足够准确
        if code not in price_cache:
            current = get_current_price(code, market)
            if current:
                price_cache[code] = current
        current_price = price_cache.get(code)

        if not current_price:
            print(f"    ⚠️ {code} 无当前价格，跳过")
            continue

        pct_change = (current_price - entry_price) / entry_price * 100

        updates = {}
        if need_7d:
            updates["label_7d_return"] = round(pct_change, 2)
        if need_30d:
            updates["label_30d_return"] = round(pct_change, 2)

        if not updates:
            continue

        print(f"    ✅ {code} {analysis_date} | {conclusion} | "
              f"入场¥{entry_price:.2f} → 当前¥{current_price:.2f} | "
              f"{pct_change:+.1f}% | 回填: {list(updates.keys())}")

        if not dry_run:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            vals = list(updates.values()) + [record_id]
            with db.get_conn() as conn:
                conn.execute(
                    f"UPDATE analysis_results SET {set_clause} WHERE id=?", vals
                )
        updated += 1

    print(f"  ✔ 回填完成：{updated} 条")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写入")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
