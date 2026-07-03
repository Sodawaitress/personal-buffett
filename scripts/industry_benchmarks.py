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
    code2ind = {}  # ticker→行业，供 ROE 分组
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
                pure = code.zfill(6)
                db.save_stock_industry(pure, name)
                code2ind[pure] = name
                done_map += 1

        if i % 20 == 0:
            print(f"  [{i}/{len(industries)}] …{done_bench} 基准 / {done_map} 映射")

    print(f"PE/PB 完成：{done_bench} 行业指标基准，{done_map} 只股票行业映射。")
    _build_roe(code2ind)


def _build_roe(code2ind, report_date=None):
    """ROE 行业基准：stock_yjbb_em 一次取全市场 ROE，按行业聚合 mean+std。"""
    import akshare as ak
    from collections import defaultdict
    import datetime as _dt

    # 选最近一个已披露的年报日期（往前找几个年末）
    dates = [report_date] if report_date else [
        f"{y}1231" for y in range(_dt.date.today().year - 1, _dt.date.today().year - 4, -1)
    ]
    df = None
    for d in dates:
        try:
            df = _retry(ak.stock_yjbb_em, date=d)
            if df is not None and len(df) > 100:
                print(f"ROE 用业绩报表 {d}，{len(df)} 条")
                break
        except Exception as e:
            print(f"  yjbb {d} 失败: {repr(e)[:60]}")
    if df is None or len(df) == 0:
        print("ROE：拿不到业绩报表，跳过（PE/PB 已够用）")
        return

    roe_col = next((c for c in df.columns if "净资产收益率" in c or "ROE" in c.upper()), None)
    code_col = next((c for c in df.columns if "代码" in c), None)
    if not roe_col or not code_col:
        print(f"ROE：列名不符（cols={list(df.columns)[:12]}…），跳过")
        return

    buckets = defaultdict(list)
    for _, row in df.iterrows():
        code = str(row[code_col]).zfill(6)
        ind = code2ind.get(code)
        if not ind:
            continue
        try:
            v = float(row[roe_col])
            if v == v and -100 < v < 200:  # 去极端/NaN
                buckets[ind].append(v)
        except (ValueError, TypeError):
            pass

    n_ind = 0
    for ind, vals in buckets.items():
        if len(vals) >= 5:
            mean = statistics.mean(vals)
            std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            db.save_industry_benchmark(ind, "roe", round(mean, 3), round(std, 3), len(vals))
            n_ind += 1
    print(f"ROE 完成：{n_ind} 个行业 ROE 基准（列={roe_col}）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="只跑前 N 个行业（调试）")
    args = ap.parse_args()
    build(args.limit)
