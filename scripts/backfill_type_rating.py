#!/usr/bin/env python3
"""
US-116 回填：用类型感知评级重评现有分析结果，并修复 market 缺失。

默认 dry-run（只打印 old→new，不写库）。加 --apply 才真正更新。
重评只动 quant 评级字段（grade/conclusion/quant_score/quant_components/
data_incomplete/reasoning），不重跑 LLM 巴菲特信——若 grade 大幅变化，
建议之后让 pipeline 重新生成信件保持一致。

用法：
  python3 scripts/backfill_type_rating.py            # dry-run 全部
  python3 scripts/backfill_type_rating.py --grade D  # 只看当前 D 的
  python3 scripts/backfill_type_rating.py --apply     # 写库
"""
import argparse
import json
import sys

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths
bootstrap_paths()

import db
from radar_app.shared.market import detect_market
from scripts.quantitative_rating import QuantitativeRater


def fix_missing_market(apply: bool):
    with db.get_conn() as c:
        rows = c.execute(
            "SELECT code FROM stocks WHERE market IS NULL OR market=''"
        ).fetchall()
    if not rows:
        print("market 缺失：无")
        return
    print(f"\n── market 缺失修复（{len(rows)} 行）──")
    for r in rows:
        code = r["code"]
        m = detect_market(code)
        print(f"  {code:14} → {m}")
        if apply:
            with db.get_conn() as c:
                c.execute("UPDATE stocks SET market=:m WHERE code=:code",
                          {"m": m, "code": code})


def rerate(grade_filter: str | None, apply: bool):
    # 取每只股票最新一条分析
    with db.get_conn() as c:
        rows = c.execute(
            """
            SELECT a.id, a.code, a.grade, a.quant_score
            FROM analysis_results a
            JOIN (SELECT code, MAX(id) mid FROM analysis_results GROUP BY code) m
              ON a.id = m.mid
            """
        ).fetchall()

    changed = 0
    print(f"\n── 重评（共 {len(rows)} 只）──")
    print(f"{'code':14}{'type':14}{'old':>6} → {'new':<5}{'q/v':>10}")
    for r in rows:
        code, old_grade = r["code"], r["grade"]
        if grade_filter and old_grade != grade_filter:
            continue

        fund = db.get_fundamentals(code) or {}
        with db.get_conn() as c:
            meta = c.execute(
                "SELECT company_type FROM stock_meta WHERE code=:code", {"code": code}
            ).fetchone()
        ctype = meta["company_type"] if meta else None
        if not ctype:
            continue  # 没分类的跳过（应先跑 classifier）
        if ctype in ("etf", "fund"):
            continue  # 基金/ETF 走专用 FundRater，不在类型评级范围内

        annual = fund.get("annual") or []
        sig = fund.get("signals") or {}
        res = QuantitativeRater().rate_stock(
            code=code, name=code, annual_data=annual,
            pe_percentile=fund.get("pe_percentile_5y"),
            pb_percentile=fund.get("pb_percentile_5y"),
            price_52week_pct=(sig or {}).get("price_position"),
            news_signals={}, locale="zh", signals=sig, company_type=ctype,
        )
        new_grade = res["grade"]
        qv = f"{res.get('quality_score')}/{res.get('value_tier') or '-'}"
        mark = "  *" if new_grade != old_grade else ""
        print(f"{code:14}{ctype:14}{(old_grade or '—'):>6} → {new_grade:<5}{qv:>10}{mark}")
        if new_grade != old_grade:
            changed += 1
        if apply:
            with db.get_conn() as c:
                c.execute(
                    """UPDATE analysis_results
                       SET grade=:g, conclusion=:c, quant_score=:s,
                           quant_components=:comp, data_incomplete=:di, reasoning=:rz
                       WHERE id=:id""",
                    {"g": new_grade, "c": res["conclusion"], "s": res["score"],
                     "comp": json.dumps(res["components"], ensure_ascii=False),
                     "di": res.get("data_incomplete", 0), "rz": res["reasoning"],
                     "id": r["id"]},
                )

    print(f"\n变化 {changed} 只。{'已写库。' if apply else 'dry-run（未写库，加 --apply 生效）。'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade", help="只重评指定等级（如 D）")
    ap.add_argument("--apply", action="store_true", help="真正写库")
    args = ap.parse_args()

    db.init_db()
    fix_missing_market(args.apply)
    rerate(args.grade, args.apply)
