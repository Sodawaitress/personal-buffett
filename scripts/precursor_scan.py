#!/usr/bin/env python3
"""
机构前兆信号每日扫描（US-69）
每个交易日 8:30 NZT 自动运行，扫描所有自选 A 股，结果存入 stock_precursor_cache。
"""

import sys, os
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gc
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime

import db
from scripts.config import CN_TZ
from scripts.precursor_signals import (
    fetch_survey_activity,
    fetch_short_selling_trend,
    fetch_inst_participation_trend,
)
from radar_app.data.core import get_conn
from radar_app.data.market import save_precursor_cache
from radar_app.data.stocks import get_all_cn_watchlist_stocks


def _get_price_changes(codes: list[str]) -> dict[str, float]:
    """从 stock_prices 取每只股票最新的涨跌幅，返回 {code: change_pct}。"""
    if not codes:
        return {}
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {f"c{i}": code for i, code in enumerate(codes)}
    with get_conn() as c:
        rows = c.execute(
            f"""
            SELECT code, change_pct FROM stock_prices
            WHERE code IN ({placeholders})
              AND fetched_at = (SELECT MAX(fetched_at) FROM stock_prices WHERE code = stock_prices.code)
            """,
            params,
        ).fetchall()
    return {r["code"]: (r["change_pct"] or 0.0) for r in rows}

_T_PER_STOCK = 30  # 单只股票融券/参与度最长等待秒数


def _call_with_timeout(fn, *args, timeout=_T_PER_STOCK, fallback=None):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout:
            return fallback if fallback is not None else {"valid": False, "desc": f"超时（>{timeout}s）"}
        except Exception as e:
            return fallback if fallback is not None else {"valid": False, "desc": str(e)}


def _compute_score(survey: dict, short_selling: dict, participation: dict) -> tuple[float, bool]:
    """
    排序用的粗略活跃度分，不做方向判断。
    调研分（上限3）+ 融券变化幅度（上限2）+ 参与度偏离均值（上限2）。
    ≥2 标为活跃，用于过滤无信号股票。价格方向由调用方单独展示，不在此处混合。
    """
    score = 0.0

    sv = survey or {}
    for ev in (sv.get("events") or []):
        score += 1.5 if ev.get("is_specific") else 0.5
    score = min(score, 3.0)

    sh = short_selling or {}
    if sh.get("valid"):
        score += min(abs(sh.get("change_pct") or 0) / 20, 2.0)

    pa = participation or {}
    if pa.get("valid") and pa.get("stdev"):
        latest = pa.get("latest") or 0
        avg    = pa.get("avg_30d") or 0
        std    = pa.get("stdev") or 1
        score += min(max((latest - avg) / std, 0), 2.0)

    return round(score, 2), score >= 2.0


def run_precursor_scan(codes: list[str] | None = None) -> dict:
    """
    对指定 A 股代码列表（默认全部自选）批量拉取前兆信号并写入缓存。
    返回 {"scanned": N, "active": M} 摘要。
    """
    if codes is None:
        pairs = get_all_cn_watchlist_stocks()
        codes = [c for c, _ in pairs]

    if not codes:
        print("  precursor_scan: 无 A 股自选股，跳过")
        return {"scanned": 0, "active": 0}

    print(f"  precursor_scan: 开始扫描 {len(codes)} 只 A 股…")
    start = time.time()

    # ── 中标/订单信号（US-131，巨潮）——**必须排在逐股扫描之前**（US-184）
    #
    # 原来它挂在 209 只循环的**后面**。那个循环按小时计，job 在 120 分钟被判死，
    # 于是中标一次都轮不到 —— 和 US-174 里「行业映射排第三被饿死」是同一个毛病，
    # 只是换了个地方。次序按「谁最容易被饿死」排：便宜的先跑（这段约 30 秒）。
    tender = {"codes_with_tender": 0, "events_saved": 0}
    try:
        from scripts.tender_signals import run_tender_refresh
        tender = run_tender_refresh(codes, days=30)
        print(f"  precursor_scan: 中标刷新 {tender}")
    except Exception as e:
        print(f"  precursor_scan: 中标刷新失败 — {e}")

    # 1. 调研：一次批量拉完（快，约 1 分钟）
    print("  precursor_scan: [1/3] 机构调研活动…")
    surveys = _call_with_timeout(fetch_survey_activity, set(codes), timeout=120, fallback={})

    # 2. 批量取最新价格涨跌幅（参与度方向判断用）
    price_changes = _get_price_changes(codes)

    # 3. 逐股拉融券+参与度，立即存库，每股最多等 30s
    active_count = 0
    for i, code in enumerate(codes):
        sv = surveys.get(code, {"score": 0, "desc": "近期无机构调研", "events": []})
        price_chg = price_changes.get(code, 0.0)

        print(f"  precursor_scan: [{i+1}/{len(codes)}] {code} 融券…", flush=True)
        short = _call_with_timeout(fetch_short_selling_trend, code)

        print(f"  precursor_scan: [{i+1}/{len(codes)}] {code} 参与度…", flush=True)
        part  = _call_with_timeout(fetch_inst_participation_trend, code)

        score, is_active = _compute_score(sv, short, part)

        if isinstance(part, dict):
            part = {**part, "price_change_pct": price_chg}

        if is_active:
            active_count += 1

        try:
            save_precursor_cache(code, sv, short, part, score, is_active)
        except Exception as e:
            print(f"  precursor_scan: 存储 {code} 失败 — {e}")

        # 每只结束后主动释放内存，避免 512MB 机器 OOM
        del short, part
        gc.collect()
        time.sleep(2)  # 给 OS 回收内存的时间，顺带限速

    elapsed = time.time() - start
    print(f"  precursor_scan: 完成 {len(codes)} 只，活跃 {active_count} 只，耗时 {elapsed:.0f}s")

    return {"scanned": len(codes), "active": active_count, "tender": tender}


if __name__ == "__main__":
    result = run_precursor_scan()
    print(result)
