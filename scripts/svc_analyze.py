#!/usr/bin/env python3
"""analyze-svc（US-121）：选择性跑 LLM 巴菲特信。

只分析 should_analyze 命中的股（持仓 / 近 2 天重大新闻 / 距上次 ≥N 天轮转 / 从未分析），
数据全从 DB 读（fetch-svc 已写好），配速器保证不撞 TPM，时间预算超了提前停下次续。
整轮 service_run 记账。独立于 fetch-svc / push-svc：本服务挂了价格仍新鲜、旧报告仍可推。
"""
import os
import sys
import time
from collections import Counter

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db
from scripts.pipeline_analysis import _run_analysis

BUDGET_MIN = float(os.environ.get("ANALYZE_BUDGET_MIN", "50"))
ROTATION_DAYS = int(os.environ.get("ANALYZE_ROTATION_DAYS", "3"))

# 预算被截断时先做要紧的：持仓 > 重大新闻 > 从未分析 > 轮转
_PRIORITY = {"held": 0, "material": 1, "never": 2, "bad_date": 2, "rotation": 3}


def main():
    codes = db.all_watched_codes()
    picked = db.select_codes_to_analyze(codes, rotation_days=ROTATION_DAYS)
    picked.sort(key=lambda cr: _PRIORITY.get(cr[1], 9))

    print(f"🤖 analyze-svc 启动：{len(picked)}/{len(codes)} 只待分析，预算 {BUDGET_MIN} 分钟")
    print(f"  选择原因: {dict(Counter(r for _, r in picked))}")
    deadline = time.time() + BUDGET_MIN * 60
    done = 0

    with db.service_run("analyze-svc") as run:
        for code, reason in picked:
            if time.time() > deadline:
                run.stopped_early = True
                print(f"⏱ 达 {BUDGET_MIN} 分钟预算，提前停止（已 {done} 只，剩 {len(picked)-done} 只下次续）")
                break

            stock = db.get_stock(code)
            if not stock:
                continue
            market = stock.get("market", "nz")

            def log(msg):
                print(f"  {msg}")

            print(f"▶ {code} ({market}) [{reason}]")
            try:
                _run_analysis(code, market, log)
                done += 1
                run.tick()
            except Exception as e:
                print(f"  ⚠️ {code} 分析失败（跳过）: {e}")

    print(f"✅ analyze-svc 完成：{done}/{len(picked)} 只")


if __name__ == "__main__":
    main()
