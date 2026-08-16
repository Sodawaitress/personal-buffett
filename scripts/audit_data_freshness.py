#!/usr/bin/env python3
"""US-154：数据源新鲜度体检 —— 哪些表在悄悄停更、哪些字段大面积拉不到。

为什么要有这个：2026-08-15 排查时，几个表被判成「停更」，但那是从本地
`data/radar.db`（旧开发库）查的，生产在 Neon 上。**不在生产环境跑的
新鲜度结论一律不算数。** 本脚本走 radar_app 的 get_conn，在 GHA 里带
DATABASE_URL 跑就是生产真相。

用法：
    python -m scripts.audit_data_freshness            # 人读的报告
    python -m scripts.audit_data_freshness --json     # 机器读

退出码恒为 0：这是体检不是门禁，不该因为发现问题就把 workflow 弄红。
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import inspect, text

from radar_app.data.core import DATABASE_URL, get_conn, get_engine

# 表 → 用来判新鲜度的时间列。写死而不是自动猜：自动猜会在
# fetched_at(写入时间) 和 trade_date(业务时间) 之间摇摆，两者语义不同。
TABLES = {
    "stock_prices":        ("fetched_at",   2,  "价格"),
    "analysis_results":    ("analysis_date", 2, "个股分析"),
    "reports":             ("analysis_date", 2, "报告"),
    "stock_news":          ("fetched_date", 2,  "个股新闻"),
    "market_news":         ("fetched_date", 2,  "市场新闻"),
    "precursor_history":   ("snapshot_date", 2, "前兆信号"),
    "block_trades":        ("trade_date",   4,  "大宗交易"),
    "insider_changes":     ("change_date",  10, "内部人增减持"),
    "stock_fund_flow":     ("date",         4,  "资金流向"),
    "northbound_history":  ("date",         4,  "北向（已知停更）"),
    "analyst_consensus":   ("fetched_at",   8,  "分析师一致预期"),
    "inst_quarterly":      ("updated_at",   95, "机构季度持仓"),
    "market_data":         ("fetched_at",   3,  "宏观快照"),
    "industry_daily":      ("date",         4,  "行业日线(US-158)"),
    "unpriced_signals":    ("created_at",   8,  "未定价信号"),
    "signal_predictions":  ("created_at",   8,  "信号预测"),
    "supply_chain_links":  ("scanned_at",  30,  "供应链"),
    "stock_fundamentals":  ("updated_at",   8,  "财务基本面"),
}


def _rows(conn, sql, **params):
    """行只支持按列名取值（get_conn 的 row factory），不能用下标。"""
    return [dict(r) for r in conn.execute(text(sql), params).fetchall()]


def _scalar(conn, sql, **params):
    """sql 必须把结果列命名为 v，例如 SELECT COUNT(*) AS v FROM t。"""
    r = conn.execute(text(sql), params).fetchone()
    return dict(r).get("v") if r else None


def audit_tables(conn, existing):
    out = []
    today = date.today()
    for table, (col, budget_days, label) in TABLES.items():
        if table not in existing:
            out.append({"table": table, "label": label, "status": "MISSING"})
            continue
        try:
            total = _scalar(conn, f"SELECT COUNT(*) AS v FROM {table}") or 0
            newest = _scalar(conn, f"SELECT MAX({col}) AS v FROM {table}")
        except Exception as e:
            out.append({"table": table, "label": label, "status": "ERROR",
                        "error": str(e)[:160]})
            continue

        age_days = None
        newest_s = str(newest)[:10] if newest else ""
        if newest_s:
            try:
                y, m, d = (int(x) for x in newest_s.split("-")[:3])
                age_days = (today - date(y, m, d)).days
            except (ValueError, TypeError):
                pass

        if total == 0:
            status = "EMPTY"
        elif age_days is None:
            status = "UNKNOWN"
        elif age_days > budget_days:
            status = "STALE"
        else:
            status = "OK"

        out.append({"table": table, "label": label, "status": status,
                    "rows": total, "newest": newest_s, "age_days": age_days,
                    "budget_days": budget_days})
    return out


def audit_moat(conn, existing):
    """财务拉取失败率：护城河 0/35 说明财务字段一个都没拿到。

    08-14 快照实测 96/210（A股 68/175）—— 近一半的股票在用残缺数据出评级。
    """
    if "analysis_results" not in existing:
        return {}
    newest = _scalar(conn, "SELECT MAX(analysis_date) AS v FROM analysis_results")
    if not newest:
        return {}
    rows = _rows(conn, """
        SELECT a.code AS code, a.moat AS moat, a.data_incomplete AS di,
               a.quant_score AS qs, s.market AS market
        FROM analysis_results a
        LEFT JOIN stocks s ON s.code = a.code
        WHERE a.analysis_date = :d
    """, d=newest)

    by_market = {}
    for r in rows:
        mkt = (r.get("market") or "unknown").lower()
        b = by_market.setdefault(mkt, {"total": 0, "moat0": 0, "incomplete": 0})
        b["total"] += 1
        if "0/35" in (r.get("moat") or ""):
            b["moat0"] += 1
        # data_quality 是展示层算出来的，DB 里只有这两个原始字段：
        # radar_app 判 incomplete 的口径 = moat 含 0/35 或 quant_score < 15
        qs = r.get("qs")
        if r.get("di") or (qs is not None and qs < 15) or "0/35" in (r.get("moat") or ""):
            b["incomplete"] += 1
    return {"as_of": str(newest)[:10], "by_market": by_market}


def audit_moat_detail(conn, existing):
    """护城河 0/35 的股票，到底有没有财务数据打底。

    区分两种情况（应对方式完全不同）：
      A. stock_fundamentals 压根没这只 → 抓取失败，可修
      B. 有财务行但护城河仍算 0 → 打分逻辑问题，不是抓取问题
    """
    if not {"analysis_results", "stock_fundamentals", "stocks"} <= existing:
        return {}
    newest = _scalar(conn, "SELECT MAX(analysis_date) AS v FROM analysis_results")
    if not newest:
        return {}
    rows = _rows(conn, """
        SELECT a.code AS code, s.market AS market,
               CASE WHEN f.code IS NULL THEN 0 ELSE 1 END AS has_fund,
               f.pe_current AS pe, f.annual_json AS annual
        FROM analysis_results a
        JOIN stocks s ON s.code = a.code
        LEFT JOIN stock_fundamentals f ON f.code = a.code
        WHERE a.analysis_date = :d AND a.moat LIKE :pat
    """, d=newest, pat="%0/35%")
    out = {}
    for r in rows:
        mkt = (r.get("market") or "unknown").lower()
        b = out.setdefault(mkt, {"moat0": 0, "no_fund_row": 0,
                                 "has_row_no_pe": 0, "has_row_no_annual": 0})
        b["moat0"] += 1
        if not r.get("has_fund"):
            b["no_fund_row"] += 1
        else:
            if r.get("pe") is None:
                b["has_row_no_pe"] += 1
            # 关键：annual_json = '[]' 作为字符串非空，解析出来却是空列表。
            # score_moat 只在 annual_data 与 signals 都空时才返回 0 分，
            # 所以「有 annual_json 但它是 []」正是护城河 0/35 的真凶候选。
            annual = r.get("annual")
            if not annual:
                b["has_row_no_annual"] += 1
            else:
                try:
                    parsed = json.loads(annual) if isinstance(annual, str) else annual
                except (ValueError, TypeError):
                    parsed = None
                if not parsed:
                    b.setdefault("annual_json_is_empty_list", 0)
                    b["annual_json_is_empty_list"] += 1
    return out


def audit_industry_coverage(conn, existing):
    """自选股里有多少拿到了行业归属（US-158 的映射覆盖率）。

    这是行业信号能否生效的前提：映射不上的股票，信号卡片根本不会出现。
    """
    if not {"stock_industry_map", "stocks", "user_watchlist"} <= existing:
        return {}
    # user_watchlist 的外键列叫 stock_code（不是 code）；
    # stock_industry_map.code 存的是纯 6 位，A 股的 stocks.code 也是纯 6 位，直接 join。
    rows = _rows(conn, """
        SELECT s.market AS market,
               COUNT(DISTINCT s.code) AS total,
               COUNT(DISTINCT CASE WHEN m.code IS NOT NULL THEN s.code END) AS mapped
        FROM stocks s
        JOIN user_watchlist w ON w.stock_code = s.code
        LEFT JOIN stock_industry_map m ON m.code = s.code
        GROUP BY s.market
    """)
    return {r["market"] or "unknown": {"total": r["total"], "mapped": r["mapped"]}
            for r in rows}


def audit_industry_gaps(conn, existing):
    """行业日线缺口 —— US-158 的自检核心。

    这个系统所有的沉默失败都是「跑了、返回了、没报错、但没产出」，
    只有查数据本身才能发现。新浪无历史接口，漏掉的天补不回来，
    所以缺口必须尽早暴露。
    """
    if "industry_daily" not in existing:
        return {}
    try:
        from scripts.industry_signals import find_gaps
        return find_gaps(30)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def audit_company_type(conn, existing):
    """industry_signals 的上游闸门：没有 company_type 就整个跳过不抓。

    生产 industry_signals 只有 1 行、26 天没更新 —— 先确认是不是被这个闸门卡住。
    """
    if "stock_meta" not in existing or "stocks" not in existing:
        return {}
    rows = _rows(conn, """
        SELECT s.market AS market,
               COUNT(*) AS total,
               SUM(CASE WHEN m.company_type IS NULL OR m.company_type = ''
                        THEN 1 ELSE 0 END) AS missing
        FROM stocks s
        LEFT JOIN stock_meta m ON m.code = s.code
        GROUP BY s.market
    """)
    return {r["market"] or "unknown": {"total": r["total"], "missing": r["missing"]}
            for r in rows}


def audit_northbound(conn, existing):
    """北向到底是「真有数」还是「每天写一堆 0」。

    US-151 是按「2026-07 起停更」的前提做的，但那个前提来自本地旧库。
    生产 northbound_history 每天都在写 —— 必须看清写进去的是不是 0.0，
    否则 stale 判定（按日期）永远不触发，而 0.0 仍会稀释评分。
    """
    if "northbound_history" not in existing:
        return {}
    rows = _rows(conn, """
        SELECT date AS d, total_net AS v FROM northbound_history
        ORDER BY date DESC LIMIT 15
    """)
    nonzero = sum(1 for r in rows if (r.get("v") or 0) != 0)
    return {"recent": [(str(r["d"])[:10], r["v"]) for r in rows],
            "nonzero_in_last_15": nonzero}


def audit_fundamentals(conn, existing):
    """财务表本身有多少行是空壳（有 code 但关键字段全 NULL）。"""
    if "stock_fundamentals" not in existing:
        return {}
    cols = {c["name"] for c in inspect(get_engine()).get_columns("stock_fundamentals")}
    probes = [c for c in ("pe_current", "pb_current", "annual_json") if c in cols]
    if not probes:
        return {"note": "stock_fundamentals 无可探测的关键字段", "columns": sorted(cols)}
    total = _scalar(conn, "SELECT COUNT(*) AS v FROM stock_fundamentals") or 0
    allnull = _scalar(conn, "SELECT COUNT(*) AS v FROM stock_fundamentals WHERE " +
                      " AND ".join(f"{c} IS NULL" for c in probes)) or 0
    return {"total": total, "all_key_fields_null": allnull, "probed": probes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    backend = DATABASE_URL.split("://")[0]
    is_prod = not DATABASE_URL.startswith("sqlite")

    with get_conn() as conn:
        existing = set(inspect(get_engine()).get_table_names())
        tables = audit_tables(conn, existing)
        moat = audit_moat(conn, existing)
        fundamentals = audit_fundamentals(conn, existing)
        northbound = audit_northbound(conn, existing)
        company_type = audit_company_type(conn, existing)
        moat_detail = audit_moat_detail(conn, existing)
        industry_gaps = audit_industry_gaps(conn, existing)
        industry_cov = audit_industry_coverage(conn, existing)

    payload = {"backend": backend, "is_production": is_prod,
               "checked_at": datetime.utcnow().isoformat() + "Z",
               "tables": tables, "moat": moat, "fundamentals": fundamentals,
               "northbound": northbound, "company_type": company_type,
               "moat_detail": moat_detail, "industry_gaps": industry_gaps,
               "industry_coverage": industry_cov}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"\n{'='*66}")
    print(f"数据源体检 · backend={backend} · {'生产' if is_prod else '⚠️ 本地库，结论不算数'}")
    print(f"{'='*66}\n")

    order = {"EMPTY": 0, "STALE": 1, "MISSING": 2, "ERROR": 3, "UNKNOWN": 4, "OK": 5}
    icon = {"OK": "✅", "STALE": "🔴", "EMPTY": "⬛", "MISSING": "❓",
            "ERROR": "💥", "UNKNOWN": "❔"}
    print(f"{'':2} {'表':22} {'最新':11} {'滞后':>6} {'预算':>5} {'行数':>8}  说明")
    print("-" * 78)
    for t in sorted(tables, key=lambda x: (order.get(x["status"], 9), x["table"])):
        age = f"{t['age_days']}d" if t.get("age_days") is not None else "-"
        print(f"{icon.get(t['status'],'?'):2} {t['table']:22} {t.get('newest','-'):11} "
              f"{age:>6} {str(t.get('budget_days','-'))+'d':>5} "
              f"{t.get('rows','-'):>8}  {t['label']}")
        if t.get("error"):
            print(f"   └─ {t['error']}")

    if moat:
        print(f"\n── 财务拉取失败率（{moat['as_of']} 当日分析）──")
        for mkt, b in sorted(moat["by_market"].items()):
            if not b["total"]:
                continue
            print(f"  {mkt:8} 共{b['total']:4} 只 · 护城河0/35 {b['moat0']:4} "
                  f"({b['moat0']*100//b['total']:3}%) · incomplete {b['incomplete']:4} "
                  f"({b['incomplete']*100//b['total']:3}%)")

    if industry_cov:
        print(f"\n── 自选股行业映射覆盖率（US-158）──")
        for mkt, b in sorted(industry_cov.items()):
            pct = b["mapped"] * 100 // b["total"] if b["total"] else 0
            print(f"  {mkt:8} {b['mapped']:4}/{b['total']:4} ({pct:3}%)")

    if industry_gaps:
        g = industry_gaps
        if g.get("error"):
            print(f"\n── 行业日线缺口 ──\n  💥 {g['error']}")
        else:
            icon = "✅" if not g["missing"] else "🔴"
            print(f"\n── 行业日线缺口（US-158）──")
            print(f"  {icon} 应有 {g['expected']} 天 · 已捕获 {g['captured']} 天 "
                  f"· 覆盖率 {g['coverage_pct']}%")
            if g["missing"]:
                print(f"     缺: {g['missing'][:12]}")

    if moat_detail:
        print(f"\n── 护城河 0/35 的股票拆解 ──")
        for mkt, b in sorted(moat_detail.items()):
            print(f"  {mkt:8} 0/35 共{b['moat0']:4} 只 · 无财务行 {b['no_fund_row']:4} "
                  f"· 有行无PE {b['has_row_no_pe']:4} · 有行无年报 {b['has_row_no_annual']:4} "
                  f"· 年报是空列表 {b.get('annual_json_is_empty_list', 0):4}")

    if company_type:
        print(f"\n── company_type 覆盖率（industry_signals 的上游闸门）──")
        for mkt, b in sorted(company_type.items()):
            got = b["total"] - b["missing"]
            pct = got * 100 // b["total"] if b["total"] else 0
            print(f"  {mkt:8} {got:4}/{b['total']:4} 只有分类 ({pct:3}%)")

    if northbound:
        print(f"\n── 北向实际数值（近 15 条）──")
        print(f"  非零条数: {northbound['nonzero_in_last_15']}/15")
        for d, v in northbound["recent"]:
            print(f"    {d}  {v}")

    if fundamentals:
        print(f"\n── stock_fundamentals 空壳率 ──")
        print(f"  {fundamentals}")

    bad = [t for t in tables if t["status"] in ("EMPTY", "STALE", "ERROR", "MISSING")]
    print(f"\n共 {len(tables)} 张表，{len(bad)} 张需要关注\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
