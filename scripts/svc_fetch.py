#!/usr/bin/env python3
"""fetch-svc（US-121）：只抓数据，不跑 LLM。

遍历全部自选股，逐只跑 1a–1c3 抓取层（复用 run_fetch_layers），写入 DB。
带时间预算：超 FETCH_BUDGET_MIN 分钟即停，剩余下次续（已抓的靠缓存新鲜度快速跳过）。
整轮用 service_run 记账，失败/提前停都留痕。

独立于 analyze-svc：本服务挂了不影响已有分析/推送；本服务成功则价格永远新鲜。
"""
import os
import sys
import time

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db
from scripts.pipeline_jobs import run_fetch_layers

BUDGET_MIN = float(os.environ.get("FETCH_BUDGET_MIN", "40"))


def main():
    codes = db.all_watched_codes()
    print(f"📡 fetch-svc 启动：{len(codes)} 只自选股，预算 {BUDGET_MIN} 分钟")
    deadline = time.time() + BUDGET_MIN * 60
    done = 0

    with db.service_run("fetch-svc") as run:
        for code in codes:
            if time.time() > deadline:
                run.stopped_early = True
                print(f"⏱ 达 {BUDGET_MIN} 分钟预算，提前停止（已 {done} 只，剩余下次续）")
                break

            stock = db.get_stock(code)
            if not stock:
                continue
            market = stock.get("market", "nz")

            def log(msg):
                print(f"  {msg}")

            print(f"▶ {code} ({market})")
            try:
                run_fetch_layers(code, market, log, force=True)
                done += 1
                run.tick()
            except Exception as e:
                print(f"  ⚠️ {code} 抓取失败（跳过）: {e}")

    print(f"✅ fetch-svc 完成：{done}/{len(codes)} 只")


if __name__ == "__main__":
    main()
