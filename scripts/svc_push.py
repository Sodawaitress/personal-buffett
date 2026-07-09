#!/usr/bin/env python3
"""push-svc（US-121）：推送。全程读 DB 最新数据，不重跑分析。

- Admin 全量报告（Bear + Discord + 全局 Server酱）：读 DB 里最新的 report md。
- Per-user 个人日报（notify_daily=1 的用户）：build_user_push_content 纯 DB 驱动，
  无重大变化则不打扰。
独立服务：analyze-svc 挂了也能把"已有的最新报告"推出去。
设 SKIP_PUSH=1 只生成不推送（云端验证用，不打扰妈妈）。
"""
import os
import sys
from datetime import datetime

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db
from scripts.config import CN_TZ, SERVERCHAN_KEY
from scripts.stock_report import build_user_push_content
from scripts.stock_pipeline import save_to_bear, send_discord_chunks, send_serverchan

SKIP_PUSH = bool(os.environ.get("SKIP_PUSH"))


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    date_str = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    print(f"📨 push-svc 启动 {date_str}" + ("（SKIP_PUSH：只生成不推送）" if SKIP_PUSH else ""))

    with db.service_run("push-svc") as run:
        # ── Admin 全量报告：读 DB 最新 ──
        rep = db.get_report() or {}
        report = rep.get("md") or ""
        if report:
            print(f"  📄 最新报告 {len(report)} 字符")
            if not SKIP_PUSH:
                save_to_bear(f"股票日报 {date_str}", report)
                send_discord_chunks(report)
                if SERVERCHAN_KEY:
                    send_serverchan(SERVERCHAN_KEY, f"自选股日报 {date_str}", report)
            run.tick()
        else:
            print("  ⚠️ DB 无报告，跳过 admin 推送")

        # ── Per-user 个人日报 ──
        try:
            push_users = db.get_users_with_daily_push()
        except Exception as e:
            push_users = []
            print(f"  ⚠️ 查询推送用户失败: {e}")

        for u in push_users:
            uid = u["id"]
            name = u.get("display_name") or u["email"]
            key = u.get("wecom_webhook", "")  # 存 SCT sendkey
            if not key:
                print(f"  ⚠️ {name} 无 wecom_webhook，跳过")
                continue

            content = build_user_push_content(uid, {}, {}, date_str)
            if not content:
                print(f"  · {name}：无重大变化，不打扰")
                continue

            print(f"  📲 {name}：{len(content)} 字符" + ("（SKIP）" if SKIP_PUSH else ""))
            if not SKIP_PUSH:
                send_serverchan(key, f"股票日报 {date_str} — {name}", content)
            run.tick()

    print("✅ push-svc 完成")


if __name__ == "__main__":
    main()
