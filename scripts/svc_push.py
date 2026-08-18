#!/usr/bin/env python3
"""push-svc（US-121 / US-123）：推送有用日报。全程读 DB 最新数据，不重跑分析。

US-123：删掉数字堆砌的旧报告（Bear/Discord/空壳），只推「今天该注意的」——
早期预警 + 评级变化 + 机构领先信号 + 催化剂 + 预言线方向，无料不推。
- Admin（role='admin'）：build_user_push_content → 全局 SERVERCHAN_KEY，只走 Server酱。
- Per-user（notify_daily=1）：同一 digest → 各自 SCT key。
设 SKIP_PUSH=1 只生成不推送（云端验证用，不打扰）。
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
from scripts.stock_report import admin_user_id, build_user_push_payload
from scripts.stock_pipeline import send_serverchan

SKIP_PUSH = bool(os.environ.get("SKIP_PUSH"))


def _commit_ledger(user_id, pending, who):
    """推送成功之后才记账（US-160）。记账失败不该让整个服务挂掉 ——
    最坏结果只是这批条目明天再推一次，比丢掉它们轻。"""
    if not pending:
        return
    try:
        from radar_app.data.push_ledger import commit_pushed
        commit_pushed(user_id, pending)
    except Exception as e:
        print(f"  ⚠️ {who} 推送台账记账失败（明天会重推这批）: {type(e).__name__}: {e}")


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    date_str = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    print(f"📨 push-svc 启动 {date_str}" + ("（SKIP_PUSH：只生成不推送）" if SKIP_PUSH else ""))

    with db.service_run("push-svc") as run:
        # ── Admin 有用日报（US-123）：一份 digest 两处用 —— 存档 + 推送 ──
        admin_id = admin_user_id()
        # US-160：算内容与记账分开 —— 干跑不该吃掉条目，发送失败也不该
        # 把条目永久吞掉（吞掉的后果是这件事再也不会提醒了）。
        content, pending = build_user_push_payload(admin_id, date_str) if admin_id else ("", [])

        # 归档 /report（US-138 归位）：与推送同源同一份，无料时存占位（US-124）
        report = (content.replace("\n详情见网页。", "").rstrip()
                  if content else f"# 今天该注意的 · {date_str}\n\n今天没有需要特别注意的变动。")
        if SKIP_PUSH:
            print(f"  📄 /report 归档 {len(report)} 字符（SKIP：干跑不写库）")
        else:
            db.save_report(date_str, html="", md=report)
            print(f"  📄 /report 已归档 {len(report)} 字符")

        if not SERVERCHAN_KEY:
            print("  ⚠️ 无 SERVERCHAN_KEY，跳过 admin 推送")
        elif content:
            print(f"  📲 admin 有用日报：{len(content)} 字符" + ("（SKIP）" if SKIP_PUSH else ""))
            if not SKIP_PUSH:
                send_serverchan(SERVERCHAN_KEY, f"今天有变化的 · {date_str}", content)
                _commit_ledger(admin_id, pending, "admin")
            run.tick()
        else:
            print("  · admin：无重大变化，不打扰")

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

            content, pending = build_user_push_payload(uid, date_str)
            if not content:
                print(f"  · {name}：无重大变化，不打扰")
                continue

            print(f"  📲 {name}：{len(content)} 字符" + ("（SKIP）" if SKIP_PUSH else ""))
            if not SKIP_PUSH:
                send_serverchan(key, f"股票日报 {date_str} — {name}", content)
                _commit_ledger(uid, pending, name)
            run.tick()

    print("✅ push-svc 完成")


if __name__ == "__main__":
    main()
