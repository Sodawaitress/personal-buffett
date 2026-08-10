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

from datetime import datetime

import db
from scripts.buffett_groq import set_call_deadline
from scripts.config import CN_TZ
from scripts.pipeline_analysis import _run_analysis, _run_layer2

BUDGET_MIN = float(os.environ.get("ANALYZE_BUDGET_MIN", "50"))
ROTATION_DAYS = int(os.environ.get("ANALYZE_ROTATION_DAYS", "3"))
# 量化刷新独立预算：绝不能侵占 LLM 的时间（US-139）
QUANT_BUDGET_MIN = float(os.environ.get("QUANT_BUDGET_MIN", "20"))

# 预算被截断时先做要紧的：持仓 > 重大新闻 > 从未分析 > 轮转
_PRIORITY = {"held": 0, "material": 1, "never": 2, "bad_date": 2, "rotation": 3}


def _refresh_quant_all(date_str: str) -> tuple[int, bool]:
    """收盘后给所有在持/观察股刷一遍 Layer 2 量化评级（零 LLM token，US-138）。

    旧 monolith 的 `_refresh_user_holdings_layer2`：A股跑 Layer 2、非 A股顺带跑
    整条 LLM。这里只保留 Layer 2 —— LLM 由下面的选择性循环按 should_analyze 决定，
    不再因为「是非 A股」就每天全量烧 token（US-121 选择性分析的本意）。

    US-139：当天已算过的跳过（`save_analysis` 本就是
    `ON CONFLICT(code, period, analysis_date)`，重算结果一样），并自带预算 ——
    否则 211 只 × 14.5s 会吃光整个 job 让 LLM 一只都跑不到（排班首日真事故）。
    """
    with db.get_conn() as c:
        rows = c.execute(
            "SELECT DISTINCT stock_code FROM user_watchlist WHERE status != 'sold'"
        ).all()
        # 一条查询拿全「今天已算过」，别 per-stock 查 —— 每趟 Neon 往返都要钱
        done = {
            r["code"]
            for r in c.execute(
                "SELECT DISTINCT code FROM analysis_results "
                "WHERE period='daily' AND analysis_date=:d",
                {"d": date_str},
            ).all()
        }
    codes = sorted({r["stock_code"] for r in rows if r["stock_code"]})
    todo = [c for c in codes if c not in done]
    if not todo:
        print(f"📊 量化评级：{len(codes)} 只今天都算过了，跳过")
        return 0, False

    print(f"📊 量化评级刷新：{len(todo)} 只待算（{len(codes) - len(todo)} 只今天已算过，跳过）"
          f"，预算 {QUANT_BUDGET_MIN} 分钟")
    deadline = time.time() + QUANT_BUDGET_MIN * 60
    ok, early = 0, False
    for code in todo:
        if time.time() > deadline:
            early = True
            print(f"  ⏱ 达 {QUANT_BUDGET_MIN} 分钟量化预算，停下（已 {ok} 只，"
                  f"剩 {len(todo) - ok} 只下次续）")
            break
        stock = db.get_stock(code)
        if not stock:
            continue
        try:
            _run_layer2(code, stock.get("market", "cn"), lambda _m: None)
            ok += 1
        except Exception as e:
            print(f"  ⚠️ {code} 量化评级失败（跳过）: {e}")
    print(f"  ✅ 量化评级完成：{ok}/{len(todo)}")
    return ok, early


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    codes = db.all_watched_codes()
    picked = db.select_codes_to_analyze(codes, rotation_days=ROTATION_DAYS)
    picked.sort(key=lambda cr: _PRIORITY.get(cr[1], 9))

    date_str = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    print(f"🤖 analyze-svc 启动：{len(picked)}/{len(codes)} 只待分析，预算 {BUDGET_MIN} 分钟")
    print(f"  选择原因: {dict(Counter(r for _, r in picked))}")
    done = 0

    with db.service_run("analyze-svc") as run:
        # 先做零 token 的量化评级（擂台/榜单/差评预警都读它），再花预算跑 LLM
        quant_early = False
        try:
            _, quant_early = _refresh_quant_all(date_str)
        except Exception as e:
            print(f"⚠️ 量化评级整体失败（不挡 LLM 分析）: {e}")

        # LLM 预算在量化跑完后才起算 —— 否则量化耗时会侵占信件时间（US-139 事故）
        deadline = time.time() + BUDGET_MIN * 60
        # 单只内部撞 429 会 sleep 450s，绕过下面「每只之间」的检查 → 预算交给 Groq 层
        # 一起守（US-140；实测 08-10 那轮就因此超预算 20 分钟）
        set_call_deadline(deadline)
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

        set_call_deadline(None)
        if quant_early:
            run.stopped_early = True

    print(f"✅ analyze-svc 完成：{done}/{len(picked)} 只")


if __name__ == "__main__":
    main()
