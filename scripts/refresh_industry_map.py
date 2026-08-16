#!/usr/bin/env python3
"""US-158：刷新 个股→行业 映射，并报告行业日线的缺口。

用法：
    python -m scripts.refresh_industry_map              # 刷新 + 报缺口
    python -m scripts.refresh_industry_map --gaps-only  # 只看缺口，不发请求
"""
import argparse
import sys

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps-only", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="行业之间的间隔秒数（两个源都会对密集请求限流）")
    args = ap.parse_args()

    db.init_db()
    from scripts.industry_signals import find_gaps, refresh_stock_industry_map

    if not args.gaps_only:
        print("🏭 刷新 个股→行业 映射（东财优先，新浪兜底）…")
        res = refresh_stock_industry_map(sleep_s=args.sleep)
        print(f"\n  本次映射 {res['mapped']} 只 · 跳过 {res.get('skipped', 0)} 个今日已刷新")
        for src, n in (res.get("by_source") or {}).items():
            print(f"    {src:6} 认领 {n} 只")
        if res["failed"]:
            print(f"  ⚠️ 失败 {len(res['failed'])} 个: {res['failed'][:10]}")
        # 一只都没映射到、且不是因为全都刷过了 → 真失败
        if res["mapped"] == 0 and not res.get("skipped"):
            print("❌ 一只都没映射到，判定失败")
            return 1

    print("\n📅 行业日线缺口检测（最近 30 个自然日的工作日）")
    g = find_gaps(30)
    print(f"  应有 {g['expected']} 天 · 已捕获 {g['captured']} 天 · 覆盖率 {g['coverage_pct']}%")
    if g["missing"]:
        print(f"  🔴 缺口 {len(g['missing'])} 天: {g['missing'][:12]}")
        print("     （新浪无历史接口，这些天补不回来——只能确保今后不再漏）")
    else:
        print("  ✅ 无缺口")
    return 0


if __name__ == "__main__":
    sys.exit(main())
