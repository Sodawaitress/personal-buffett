#!/usr/bin/env python3
"""
US-116 v2 行业中性化：从东财行业成分股算各行业 PE/PB 的 mean+std，
写入 industry_benchmarks；同时把 ticker→行业 写进 stock_meta.industry_em。

为什么用东财不用申万：这版 AKShare 的申万成分接口坏了（sw_index_third_cons
列数不匹配、second_cons 不存在），而东财 stock_board_industry_cons_em 稳且
成分股直接带"市盈率-动态"/"市净率"，一次拿到 membership + 估值。

本次只做 PE/PB（cons_em 不带 ROE）。ROE/毛利行业-z 待另拉每股 ROE 再补。

月度运行：python3 scripts/industry_benchmarks.py [--limit N]（--limit 调试用）
"""
import argparse
import statistics
import time

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths
bootstrap_paths()

import db


def _retry(fn, *a, tries=3, pause=3, **kw):
    """AKShare 端点偶发断连，重试几次。"""
    last = None
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as e:
            last = e
            time.sleep(pause * (i + 1))
    raise last


def _clean(series):
    """去掉 None/NaN/<=0（PE<=0 无意义），返回 float 列表。"""
    out = []
    for v in series:
        try:
            f = float(v)
            if f == f and f > 0:
                out.append(f)
        except (ValueError, TypeError):
            pass
    return out


def build(limit=None):
    import akshare as ak
    db.init_db()
    db._migrate()  # 确保 stock_meta.industry_em 等列存在

    names = _retry(ak.stock_board_industry_name_em)
    industries = list(dict.fromkeys(names["板块名称"].tolist()))  # 去重保序
    if limit:
        industries = industries[:limit]
    print(f"东财行业 {len(industries)} 个，开始拉成分…")

    done_bench, done_map = 0, 0
    for i, name in enumerate(industries, 1):
        try:
            cons = _retry(ak.stock_board_industry_cons_em, symbol=name)
        except Exception as e:
            print(f"  [{i}/{len(industries)}] {name} 成分失败: {repr(e)[:80]}")
            continue

        pe = _clean(cons.get("市盈率-动态", []))
        pb = _clean(cons.get("市净率", []))
        for metric, vals in (("pe", pe), ("pb", pb)):
            if len(vals) >= 5:  # 样本太少不可信
                mean = statistics.mean(vals)
                std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                db.save_industry_benchmark(name, metric, round(mean, 3), round(std, 3), len(vals))
                done_bench += 1

        # ticker→行业 映射（代码列名兼容）
        code_col = "代码" if "代码" in cons.columns else ("股票代码" if "股票代码" in cons.columns else None)
        if code_col:
            for code in cons[code_col].astype(str):
                db.save_stock_industry(code.zfill(6), name)
                done_map += 1

        if i % 20 == 0:
            print(f"  [{i}/{len(industries)}] …{done_bench} 基准 / {done_map} 映射")

    print(f"完成：{done_bench} 行业指标基准，{done_map} 只股票行业映射。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="只跑前 N 个行业（调试）")
    args = ap.parse_args()
    build(args.limit)
