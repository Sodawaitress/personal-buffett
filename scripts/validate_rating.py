#!/usr/bin/env python3
"""
US-116 评级验证工具（认真找的专业方法）。

自包含、不依赖坏掉的 backfill：直接从 stock_prices 历史快照，按 analysis_date
匹配"分析当日价"与"分析后 N 天价"，算真实前瞻收益，再算：
  - RankIC：评分(quant_score)与前瞻收益的秩相关（Spearman）——行业核心指标
  - 分档单调性：按 grade 分档看平均前瞻收益，A>…>D 是否单调 + 多空价差
  - 命中率：买入类评级里正收益占比

防坑：只用分析日之后的价格（无前视）；报告样本量并对小样本给警告。
局限：只覆盖自选股（幸存者偏差）；历史 grade 是当前生产系统的（新系统需部署后重跑）。

用法：python3 scripts/validate_rating.py [--horizon 30]
在 Fly 上跑才是生产基线；本地跑验证工具本身正确。
"""
import argparse
from datetime import datetime, timedelta

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths
bootstrap_paths()

import db

_GRADE_SCORE = {"A": 7, "B+": 6, "B": 5, "B-": 4, "C+": 3, "C": 2, "D": 1, "NR": None}
_BUY = {"买入"}


def _spearman(xs, ys):
    """秩相关（不依赖 scipy）：把两列转秩，算 Pearson。"""
    n = len(xs)
    if n < 5:
        return None
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return num / (dx * dy) if dx and dy else None


def _price_near(prices, target_date, window=7):
    """prices: [(date, price)] 升序；返回 target_date 当日或之后 window 天内最近的价。"""
    for d, p in prices:
        if d >= target_date and (d - target_date).days <= window:
            return p
    return None


def validate(horizon=30):
    with db.get_conn() as c:
        analyses = [dict(r) for r in c.execute(
            "SELECT code, analysis_date, grade, quant_score, conclusion FROM analysis_results "
            "WHERE period='daily' AND grade IS NOT NULL"
        )]
        prices_raw = [dict(r) for r in c.execute(
            "SELECT code, fetched_at, price FROM stock_prices ORDER BY code, fetched_at"
        )]

    # 按 code 整理价格序列 [(date, price)]
    by_code = {}
    for r in prices_raw:
        try:
            d = datetime.strptime(str(r["fetched_at"])[:10], "%Y-%m-%d").date()
            by_code.setdefault(r["code"], []).append((d, float(r["price"])))
        except (ValueError, TypeError):
            pass

    pairs = []  # (grade, quant_score, fwd_return, conclusion)
    for a in analyses:
        prices = by_code.get(a["code"])
        if not prices:
            continue
        try:
            adate = datetime.strptime(str(a["analysis_date"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        base = _price_near(prices, adate)
        fwd = _price_near(prices, adate + timedelta(days=horizon))
        if base and fwd and base > 0:
            ret = (fwd / base - 1) * 100
            pairs.append((a["grade"], a["quant_score"], ret, a["conclusion"] or ""))

    n = len(pairs)
    print(f"\n═══ 评级验证（前瞻 {horizon} 天）═══")
    print(f"可用样本：{n} 条（有分析 + 匹配到分析日和 {horizon} 天后价格）")
    if n < 20:
        print("⚠️ 样本 <20，结果只能当极初步参考，不能下结论。")
    if n < 5:
        print("样本太少，无法计算。需要 backfill 更多历史价格或等数据积累。")
        return

    # RankIC：quant_score vs 前瞻收益
    scored = [(s, r) for g, s, r, _ in pairs if s is not None]
    if len(scored) >= 5:
        ic = _spearman([s for s, _ in scored], [r for _, r in scored])
        print(f"\nRankIC（quant_score × 前瞻收益）：{ic:+.3f}（{len(scored)} 条）"
              if ic is not None else "RankIC：无法计算")
        print("  参考：|IC|>0.03 就算有效信号（行业里 0.05 已不错）；正=评分越高收益越高")

    # 分档单调性
    print("\n分档平均前瞻收益：")
    buckets = {}
    for g, s, r, _ in pairs:
        buckets.setdefault(g, []).append(r)
    order = ["A", "B+", "B", "B-", "C+", "C", "D"]
    means = {}
    for g in order:
        if g in buckets:
            m = sum(buckets[g]) / len(buckets[g])
            means[g] = m
            print(f"  {g:3} : {m:+6.2f}%  （{len(buckets[g])} 只）")
    if "A" in means and "D" in means:
        print(f"  多空价差 A−D：{means['A'] - means['D']:+.2f}%（正=评级有区分力）")

    # 命中率
    buys = [r for g, s, r, c in pairs if c in _BUY]
    if buys:
        hit = sum(1 for r in buys if r > 0) / len(buys) * 100
        print(f"\n买入类命中率（前瞻为正）：{hit:.0f}%（{len(buys)} 条）")

    print("\n局限：幸存者偏差（只自选股）；历史 grade 为当前生产系统（新系统需部署后重跑）。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=30, help="前瞻天数")
    args = ap.parse_args()
    validate(args.horizon)
