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


def _price_on_or_after(code: str, target_date: str, slack_days: int = 5):
    """取 target_date 当天或之后最近的收盘价（US-155）。

    target_date 常落在周末/长假，所以要往后找 slack_days 天；找不到就返回
    None 让调用方跳过，**绝不退回用当前价冒充历史价**——那会把 7d/30d 标签
    写成「至今收益」，准确率页拿它算命中率会得出完全错误的结论。
    """
    end = (datetime.strptime(target_date, "%Y-%m-%d")
           + timedelta(days=slack_days)).strftime("%Y-%m-%d")
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT price FROM stock_prices "
            "WHERE code=:code AND fetched_at >= :start AND fetched_at <= :end "
            "ORDER BY fetched_at ASC LIMIT 1",
            {"code": code, "start": target_date, "end": end + " 23:59:59"},
        ).fetchone()
    return row["price"] if row and row["price"] else None


def backfill(dry_run: bool = False):
    today = datetime.now(CN_TZ)
    today_str = today.strftime("%Y-%m-%d")
    # 7 天前才可能有 7d 收益可算；比这新的记录捞出来也只能 continue
    cutoff_7d = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    with db.get_conn() as conn:
        # 找所有缺 7d 或 30d 标注的分析记录
        rows = conn.execute("""
            SELECT ar.id, ar.code, ar.analysis_date, ar.conclusion,
                   ar.feat_price_momentum,
                   -- US-155：这两列 WHERE 里用了、下面 row[...] 也读了，
                   -- 但一直没 SELECT 出来 → NoSuchColumnError，每次必崩。
                   -- get_conn 的 row 只按列名取值，漏 SELECT 不会静默返回 None。
                   ar.label_7d_return, ar.label_30d_return,
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
              -- US-155：只捞真正够钟的。原来没这个条件 + ORDER BY DESC LIMIT 100
              -- ＝ 每次只拿最新 100 条，而最新的必然不满 7 天，need_7d 恒 False
              -- → 「找到 100 条，回填 0 条」，这个回填从设计上跑不出任何结果。
              AND ar.analysis_date <= :cutoff_7d
            -- 最老的先回填：越老的记录价格越可能被清理掉，先救它们
            ORDER BY ar.analysis_date ASC
            LIMIT 100
        """, {"cutoff_7d": cutoff_7d}).fetchall()

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
            price_row = conn.execute(
                "SELECT price FROM stock_prices WHERE code=:code AND fetched_at LIKE :pat "
                "ORDER BY fetched_at ASC LIMIT 1",
                {"code": code, "pat": f"{analysis_date}%"},
            ).fetchone()

        entry_price = price_row["price"] if price_row else None
        if not entry_price:
            with db.get_conn() as conn:
                price_row = conn.execute(
                    "SELECT price FROM stock_prices WHERE code=:code AND fetched_at <= :cutoff "
                    "ORDER BY fetched_at DESC LIMIT 1",
                    {"code": code, "cutoff": analysis_date + " 23:59:59"},
                ).fetchone()
            entry_price = price_row["price"] if price_row else None

        if not entry_price:
            print(f"    ⚠️ {code} {analysis_date} 无入场价，跳过")
            continue

        # US-155：目标日价格必须查历史，不能用当前实时价。
        #
        # 原实现的注释写着「简化：用当前实时价代替历史价，对于近期分析已足够准确」——
        # 这个假设只在「脚本每天跑、恰好在第 7 天回填」时成立。但 backfill() 因为
        # SELECT 漏列 + ORDER BY DESC LIMIT 100 两个 bug 从来没成功跑过，
        # 现在一跑就是拿今天的价去填 4 个月前的记录，把 7d 和 30d 写成同一个
        # 「至今收益」。那比空着更糟：准确率页会拿这些假标签算命中率。
        updates = {}
        for need, horizon, col in ((need_7d, 7, "label_7d_return"),
                                   (need_30d, 30, "label_30d_return")):
            if not need:
                continue
            target = (analysis_dt + timedelta(days=horizon)).strftime("%Y-%m-%d")
            tgt_price = _price_on_or_after(code, target, slack_days=5)

            if tgt_price is None and days_elapsed <= horizon + 2:
                # 刚够钟、历史里还没落库 → 用实时价是合理近似（原设计的本意）
                if code not in price_cache:
                    cur = get_current_price(code, market)
                    if cur:
                        price_cache[code] = cur
                tgt_price = price_cache.get(code)

            if tgt_price is None:
                print(f"    ⚠️ {code} {analysis_date} 缺 {horizon}d 目标日价格，跳过该项")
                continue
            updates[col] = round((tgt_price - entry_price) / entry_price * 100, 2)

        if not updates:
            continue

        detail = " ".join(f"{k.replace('label_','').replace('_return','')}:{v:+.1f}%"
                          for k, v in updates.items())
        print(f"    ✅ {code} {analysis_date} | {conclusion} | "
              f"入场¥{entry_price:.2f} | {detail}")

        if not dry_run:
            set_clause = ", ".join(f"{k}=:{k}" for k in updates)
            params = {**updates, "rid": record_id}
            with db.get_conn() as conn:
                conn.execute(
                    f"UPDATE analysis_results SET {set_clause} WHERE id=:rid", params
                )
        updated += 1

    print(f"  ✔ 回填完成：{updated} 条")


def backfill_predictions(dry_run: bool = False):
    """US-75 / US-92 · 回填 signal_predictions 的 actual_return_5d/10d + correct。"""
    today = datetime.now(CN_TZ)
    cutoff5  = (today - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff10 = (today - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")

    with db.get_conn() as conn:
        # 5d未回填 或 10d未回填 均需处理
        rows = conn.execute("""
            SELECT sp.id, sp.code, sp.direction, sp.created_at,
                   sp.actual_return_5d, sp.actual_return_10d,
                   sp.signal_type, sp.predicted_outcome,
                   s.market
            FROM signal_predictions sp
            JOIN stocks s ON s.code = sp.code
            WHERE (
              (sp.created_at <= :c5 AND sp.actual_return_5d IS NULL)
              OR (sp.created_at <= :c10 AND sp.actual_return_10d IS NULL)
            )
        """, {"c5": cutoff5, "c10": cutoff10}).fetchall()

    print(f"  📋 signal_predictions 待回填: {len(rows)} 条")
    price_cache: dict[str, float] = {}
    updated = 0

    for row in rows:
        code    = row["code"]
        market  = row["market"] or "cn"
        created = row["created_at"][:10]

        # Entry price: price snapshot on creation day
        with db.get_conn() as conn:
            pr = conn.execute(
                "SELECT price FROM stock_prices WHERE code=:code AND fetched_at LIKE :pat "
                "ORDER BY fetched_at ASC LIMIT 1",
                {"code": code, "pat": f"{created}%"},
            ).fetchone()
        entry_price = pr["price"] if pr else None

        if not entry_price:
            print(f"    ⚠️ {code} {created} 无入场价，跳过")
            continue

        if code not in price_cache:
            current = get_current_price(code, market)
            if current:
                price_cache[code] = current
        current_price = price_cache.get(code)

        if not current_price:
            print(f"    ⚠️ {code} 无当前价格，跳过")
            continue

        ret5d = round((current_price - entry_price) / entry_price * 100, 2)
        direction = row["direction"]
        if direction == "up":
            correct = 1 if ret5d > 3 else (0 if ret5d < -3 else None)
        elif direction == "down":
            correct = 1 if ret5d < -3 else (0 if ret5d > 3 else None)
        else:
            correct = None

        # 10d return: only compute if 10d have elapsed and not yet filled
        need_10d = row["actual_return_10d"] is None
        created_dt = datetime.fromisoformat(row["created_at"].replace(" ", "T"))
        if created_dt.tzinfo is None:
            from radar_app.shared.runtime import CN_TZ as _tz
            created_dt = created_dt.replace(tzinfo=_tz)
        elapsed_days = (today - created_dt).total_seconds() / 86400
        ret10d = None
        if need_10d and elapsed_days >= 10:
            ret10d = ret5d  # reuse current price for now (same snapshot in backfill)

        now_str = today.strftime("%Y-%m-%d %H:%M:%S")
        print(f"    ✅ {code} {created} | {direction} | "
              f"¥{entry_price:.2f}→¥{current_price:.2f} | 5d:{ret5d:+.1f}%"
              f"{' 10d:' + f'{ret10d:+.1f}%' if ret10d is not None else ''} | correct={correct}")

        if not dry_run:
            need_5d = row["actual_return_5d"] is None
            updates = {"ts": now_str, "rid": row["id"]}
            set_clauses = ["resolved_at=:ts"]
            if need_5d:
                updates.update({"r5": ret5d, "c": correct})
                set_clauses += ["actual_return_5d=:r5", "correct=:c"]
            if ret10d is not None:
                updates["r10"] = ret10d
                set_clauses.append("actual_return_10d=:r10")
            if len(set_clauses) > 1:  # more than just resolved_at
                with db.get_conn() as conn:
                    conn.execute(
                        f"UPDATE signal_predictions SET {', '.join(set_clauses)} WHERE id=:rid",
                        updates,
                    )
        updated += 1

    print(f"  ✔ 预测回填完成：{updated} 条")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写入")
    parser.add_argument("--predictions-only", action="store_true", help="只回填预测，不回填分析")
    args = parser.parse_args()
    if args.predictions_only:
        backfill_predictions(dry_run=args.dry_run)
    else:
        backfill(dry_run=args.dry_run)
        backfill_predictions(dry_run=args.dry_run)
