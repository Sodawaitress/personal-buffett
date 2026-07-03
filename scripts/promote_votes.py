#!/usr/bin/env python3
"""
US-116 验证层：把众包投票(stock_type_votes)在满足采信门后，提升为权威分类。
用户投票永远只进 stock_type_votes；是否采信由这个独立流程决定（供 admin / Claude routine 定期跑）。

采信门（研究锚定，客观任务标准 + 小用户量适配）：
  - ≥3 票 且 单一类型占比 ≥67%（3人多数票，客观任务标准）
  - 与 auto 一致 → CONFIRM（低风险，可 --apply 采纳，标 type_source='crowd' 防被重分类覆盖）
  - 与 auto 冲突 → REVIEW（默认只报告，人工/routine 拍板；--apply-conflicts 才写）
  - manual_override 的（专家已定）→ 跳过，专家优先
专家加权：admin 通过 admin.py 设 manual_override（不走这个投票流程）。
（未来：投票加 user_id 做可靠性加权；outcome 验证=该分类尺子 RankIC 更好才采信）

用法：
  python3 scripts/promote_votes.py                 # 只报告
  python3 scripts/promote_votes.py --apply         # 采纳"一致"共识
  python3 scripts/promote_votes.py --apply-conflicts  # 连"冲突"共识也写（人工复核后）
"""
import argparse
from collections import Counter

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths
bootstrap_paths()

import db

MIN_VOTES = 3
MIN_AGREE = 0.67


def _apply(code, ctype):
    with db.get_conn() as c:
        c.execute(
            "UPDATE stock_meta SET company_type=:t, type_source='crowd' WHERE code=:code",
            {"t": ctype, "code": code},
        )


def promote(apply=False, apply_conflicts=False):
    db.init_db(); db._migrate()
    with db.get_conn() as c:
        rows = c.execute("SELECT code, company_type FROM stock_type_votes").all()
    votes = {}
    for r in rows:
        votes.setdefault(r["code"], []).append(r["company_type"])

    n_confirm = n_review = n_insuf = n_applied = 0
    print(f"\n═══ 众包分类采信（门槛 ≥{MIN_VOTES}票/{MIN_AGREE:.0%}）═══")
    for code, vlist in sorted(votes.items()):
        meta = db.get_stock_meta(code) or {}
        if meta.get("manual_override") or meta.get("type_source") == "manual":
            continue  # 专家已定，跳过
        auto = meta.get("company_type")
        cnt = Counter(vlist)
        top, top_n = cnt.most_common(1)[0]
        share = top_n / len(vlist)

        if len(vlist) < MIN_VOTES or share < MIN_AGREE:
            n_insuf += 1
            continue

        if top == auto:
            n_confirm += 1
            tag = "CONFIRM 一致"
            if apply:
                _apply(code, top); n_applied += 1; tag += " ✓已采纳"
            print(f"  {code:10} {tag:16} {top}（{top_n}/{len(vlist)}）")
        else:
            n_review += 1
            tag = "REVIEW 冲突"
            if apply_conflicts:
                _apply(code, top); n_applied += 1; tag += " ✓已改"
            print(f"  {code:10} {tag:16} auto={auto} → 众包={top}（{top_n}/{len(vlist)} = {share:.0%}）⚠ 需人工复核")

    print(f"\n一致 {n_confirm} · 冲突待审 {n_review} · 票不够 {n_insuf} · 本次写库 {n_applied}")
    if not apply and not apply_conflicts:
        print("（只报告，未写库。--apply 采纳一致；--apply-conflicts 连冲突也写）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="采纳与auto一致的共识")
    ap.add_argument("--apply-conflicts", action="store_true", help="连冲突共识也写（人工复核后）")
    args = ap.parse_args()
    promote(args.apply, args.apply_conflicts)
