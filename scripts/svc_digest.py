#!/usr/bin/env python3
"""digest-svc（US-121）：快照 commit + 预测收益回填。

- run_daily_digest(): 从 DB 汇总全平台自选股 → 构建快照 JSON → commit 到 GitHub。
- backfill_predictions(): 回填历史预测的实际收益（5d/10d）。
两件都是纯 DB 驱动、无 LLM 的轻活。独立服务：不依赖 analyze-svc 是否跑完（读 DB 最新价）。
"""
import sys

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    print("📸 digest-svc 启动")
    with db.service_run("digest-svc") as run:
        # 快照 + commit
        from scripts.daily_digest import run_daily_digest
        committed = run_daily_digest()
        run.tick()
        if committed:
            print("  ✅ 快照已构建并提交 GitHub")
        else:
            # 别再打 ✅ 糊过去：提交失败 = Routine 继续读陈旧快照（US-140，冻了 14 天没人知道）
            print("  ❌ 快照未能提交 GitHub —— Routine 会继续读到陈旧快照")

        # 预测收益回填（挂了不影响快照）
        try:
            from scripts.backfill_returns import backfill_predictions
            backfill_predictions()
            run.tick()
            print("  ✅ 预测收益回填完成")
        except Exception as e:
            print(f"  ⚠️ 回填失败（不影响快照）: {e}")

        # 回填先跑完（它不依赖快照），再让服务失败 → service_runs 记 failed + 告警响
        if not committed:
            raise RuntimeError("快照未提交 GitHub（详见上方日志：403=权限/401=token/熔断）")

    print("✅ digest-svc 完成")


if __name__ == "__main__":
    main()
