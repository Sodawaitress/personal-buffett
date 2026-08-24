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


def audit_users(conn, existing):
    """多用户系统的账号概览：谁有多少自选股、推送开没开。

    **邮箱只保留域名**（如 ***@qq.com）—— 识别账号够用，不把完整地址
    打进 CI 日志。这是私有仓库，但没必要把 PII 往日志里堆。
    """
    if not {"users", "user_watchlist"} <= existing:
        return []
    # 带上推送设置：一个有 198 只自选股但收不到推送的账号，
    # 和一个有 2 只自选股却天天收推送的账号，长得完全不一样但都「正常」。
    # 不把这两列放一起看，这种错配就永远发现不了。
    rows = _rows(conn, """
        SELECT u.id AS id, u.email AS email, u.display_name AS name,
               u.role AS role,
               COALESCE(ps.notify_daily, 0) AS daily,
               CASE WHEN COALESCE(ps.wecom_webhook, '') <> '' THEN 1 ELSE 0 END AS hook,
               COUNT(DISTINCT CASE WHEN w.removed_at IS NULL
                                   THEN w.stock_code END) AS n
        FROM users u
        LEFT JOIN user_watchlist w ON w.user_id = u.id
        LEFT JOIN user_push_settings ps ON ps.user_id = u.id
        GROUP BY u.id, u.email, u.display_name, u.role, ps.notify_daily, ps.wecom_webhook
        ORDER BY u.id
    """)
    out = []
    for r in rows:
        em = str(r.get("email") or "")
        dom = ("***@" + em.split("@", 1)[1]) if "@" in em else "(无邮箱)"
        out.append({"id": r["id"], "domain": dom,
                    "name": r.get("name") or "", "role": r.get("role") or "",
                    "watchlist": r["n"], "daily": r["daily"], "hook": r["hook"]})
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
    out = {r["market"] or "unknown": {"total": r["total"], "mapped": r["mapped"]}
           for r in rows}

    # US-161：按来源拆开。东财只能在 Fly 上跑（封数据中心 IP），所以
    # 「em: 行数是 0」= Fly 那条路没通，而不是覆盖率天然只能到 57%。
    # 不拆来源的话这两种情况长得一样，会一直误判成「新浪的结构性上限」。
    try:
        srcs = _rows(conn, """
            SELECT CASE
                     WHEN industry LIKE :em   THEN 'em'
                     WHEN industry LIKE :sina THEN 'sina'
                     ELSE 'legacy'
                   END AS src,
                   COUNT(*) AS n
            FROM stock_industry_map
            GROUP BY 1
        """, em='%"em:%', sina='%"sina:%')
        out["_by_source"] = {r["src"]: r["n"] for r in srcs}
    except Exception as e:
        out["_by_source"] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
    return out


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


def audit_survey_followthrough(conn, existing):
    """US-167：调研后续到底判得出来多少 —— 也就是 stock_prices 够不够密。

    调研信号的方向靠「调研之后 20 天股价怎么走」推导，而这要求当时前后
    都有价格行。本地库每只只有约 21 行，绝大多数事件只能标 pending；
    生产每只约 100 行。**这一节存在的意义就是：别再拿本地密度替生产下结论**
    （本会话已经因此误判过 5 个数据源为「陈旧」）。

    decided_rate 太低 = 页面上那块「调研之后发生了什么」大面积说不出话。
    """
    if "stock_prices" not in existing or "stock_precursor_cache" not in existing:
        return {}
    from scripts.survey_followthrough import build, db_price_lookup

    rows = _rows(conn, "SELECT DISTINCT code FROM stock_precursor_cache LIMIT 60")
    price_rows = _scalar(conn, "SELECT COUNT(*) AS v FROM stock_prices") or 0
    price_codes = _scalar(conn, "SELECT COUNT(DISTINCT code) AS v FROM stock_prices") or 0

    checked = decided = pending = directional = 0
    for r in rows:
        code = r["code"]
        try:
            from radar_app.data.market import get_precursor_cache
            sv = (get_precursor_cache(code) or {}).get("survey") or {}
            events = (sv.get("events") or [])[:8]
            if not events:
                continue
            ft = build(events, db_price_lookup(code))
            sm = ft.get("summary") or {}
            checked += 1
            pending += sm.get("pending", 0)
            decided += sm.get("up", 0) + sm.get("down", 0) + sm.get("flat", 0)
            if ft.get("direction") in ("bull", "bear"):
                directional += 1
        except Exception:
            continue

    total_ev = decided + pending
    return {
        "price_rows": price_rows,
        "price_codes": price_codes,
        "rows_per_code": round(price_rows / price_codes, 1) if price_codes else 0,
        "stocks_with_surveys": checked,
        "events_decided": decided,
        "events_pending": pending,
        "decided_rate_pct": round(decided * 100 / total_ev, 1) if total_ev else 0,
        "stocks_with_direction": directional,
    }


def audit_industry_gap_detail(conn, existing):
    """US-169：自选里没有行业映射的 A股 到底是些什么。

    覆盖率 60% 这个数字本身没法指导决策 —— 缺的若都是 ETF，那不是缺陷；
    若都是正常个股，就是上游 refresh 没跑全。看样本再决定。
    """
    if "stock_industry_map" not in existing:
        return {}
    rows = _rows(conn, """
        SELECT s.code, s.name, COALESCE(s.asset_type,'') AS at
        FROM stocks s
        WHERE s.market = 'cn'
          AND s.code IN (SELECT DISTINCT stock_code FROM user_watchlist
                         WHERE removed_at IS NULL)
          AND s.code NOT IN (SELECT code FROM stock_industry_map)
        ORDER BY s.code LIMIT 25
    """)
    by_type = _rows(conn, """
        SELECT COALESCE(s.asset_type,'(空)') AS at, COUNT(*) AS n
        FROM stocks s
        WHERE s.market = 'cn'
          AND s.code IN (SELECT DISTINCT stock_code FROM user_watchlist
                         WHERE removed_at IS NULL)
          AND s.code NOT IN (SELECT code FROM stock_industry_map)
        GROUP BY 1 ORDER BY 2 DESC
    """)
    return {"sample": [(r["code"], r["name"], r["at"]) for r in rows],
            "by_asset_type": {r["at"]: r["n"] for r in by_type}}


def audit_em_convergence(conn, existing):
    """US-158 东财映射的实际收敛速度 —— 决定行业筛选多久才真的可用。

    设计是每天 12 个板块、约 8 天覆盖 100 个板块。但 502 是按 IP 限流的，
    实际能刷成几个板块看当天运气，所以要报**实测**进度，不能拿设计值当承诺。

    注意 stock_industry_map 没有 source 列 —— 来源编码在 industry 这个
    JSON 文本的标签前缀里（"em:BKxxxx" / "sina:xxx"），和 audit_industry_coverage
    用的是同一套判据。
    """
    if "stock_industry_map" not in existing:
        return {}
    out = {}
    try:
        out["em_total"] = _scalar(conn,
            "SELECT COUNT(*) AS v FROM stock_industry_map WHERE industry LIKE :p",
            p='%"em:%') or 0
        rows = _rows(conn, """
            SELECT substr(updated_at,1,10) AS d, COUNT(*) AS n
            FROM stock_industry_map WHERE industry LIKE :p
            GROUP BY 1 ORDER BY 1 DESC LIMIT 8
        """, p='%"em:%')
        out["em_by_day"] = [(str(r["d"]), r["n"]) for r in rows]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out


def audit_scan_jobs(conn, existing):
    """最近的 trigger-scan 任务状态和错误原文。

    US-158 的东财映射搭 trigger-scan 的车跑，8/22 之后一条新映射都没有。
    routes.py 会把「板块列表拉不到」「全部板块失败」写进 job.error，
    所以停滞的原因应该就在这里 —— 不用猜。
    """
    if "pipeline_jobs" not in existing:
        return {}
    try:
        rows = _rows(conn, """
            SELECT id, job_type, status, started_at, error
            FROM pipeline_jobs WHERE job_type LIKE '%scan%'
            ORDER BY id DESC LIMIT 10
        """)
        return {"recent": [(r["id"], r["job_type"], r["status"],
                            str(r["started_at"])[:16], (r["error"] or "")[:240])
                           for r in rows]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:140]}"}


def audit_watchlist_filter(conn, existing):
    """自选页筛选：等级词汇表一致性 + 那条 GROUP BY 在生产跑不跑得通。

    /api/watchlist/filter 里的子查询是
        SELECT code, grade, MAX(id) FROM analysis_results GROUP BY code
    `grade` 既不在 GROUP BY 里也没被聚合。SQLite 容忍（随便挑一行），
    **Postgres 直接报错**。本地测不出来 —— 所以这条探针必须跑在生产上。
    """
    if "analysis_results" not in existing:
        return {}
    out = {}

    # 真实等级分布：前端按钮写死的那串是不是真的对得上
    try:
        rows = _rows(conn, """
            SELECT UPPER(COALESCE(a.grade,'NR')) AS g, COUNT(*) AS n FROM (
                SELECT DISTINCT ON (code) code, grade FROM analysis_results
                ORDER BY code, id DESC
            ) a GROUP BY 1 ORDER BY 2 DESC
        """) if not DATABASE_URL.startswith("sqlite") else _rows(conn, """
            SELECT UPPER(COALESCE(grade,'NR')) AS g, COUNT(*) AS n FROM (
                SELECT code, grade FROM analysis_results
                WHERE id IN (SELECT MAX(id) FROM analysis_results GROUP BY code)
            ) GROUP BY 1 ORDER BY 2 DESC
        """)
        out["grades"] = {r["g"]: r["n"] for r in rows}
    except Exception as e:
        out["grades_error"] = str(e)[:200]

    # 现役筛选查询能不能在生产真的跑（US-168 修复后的形状）。
    # 旧形状 SELECT code, grade, MAX(id) ... GROUP BY code 在 Postgres 直接报
    # GroupingError，而本地 SQLite 一路绿灯 —— 这条探针就是为了不再重演。
    try:
        _rows(conn, """
            SELECT w.stock_code FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            LEFT JOIN analysis_results a
              ON a.id = (SELECT MAX(r.id) FROM analysis_results r
                         WHERE r.code = w.stock_code)
            WHERE w.removed_at IS NULL
              AND UPPER(COALESCE(a.grade,'')) = :g
            LIMIT 5
        """, g="A")
        out["filter_query"] = "OK"
    except Exception as e:
        out["filter_query"] = "FAILS: " + str(e).split("\n")[0][:160]
    return out


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
        users = audit_users(conn, existing)
        survey_ft = audit_survey_followthrough(conn, existing)
        wl_filter = audit_watchlist_filter(conn, existing)
        ind_gap = audit_industry_gap_detail(conn, existing)
        em_conv = audit_em_convergence(conn, existing)
        scan_jobs = audit_scan_jobs(conn, existing)

    payload = {"backend": backend, "is_production": is_prod,
               "checked_at": datetime.utcnow().isoformat() + "Z",
               "tables": tables, "moat": moat, "fundamentals": fundamentals,
               "survey_followthrough": survey_ft, "watchlist_filter": wl_filter, "industry_gap": ind_gap, "em_convergence": em_conv, "scan_jobs": scan_jobs,
               "northbound": northbound, "company_type": company_type,
               "moat_detail": moat_detail, "industry_gaps": industry_gaps,
               "industry_coverage": industry_cov, "users": users}

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

    if users:
        print(f"\n── 账号概览 ──")
        print(f"  {'id':>3} {'邮箱域':16}{'名字':14}{'角色':8}{'自选':>5}{'日推':>5}{'webhook':>8}  收得到吗")
        for u in users:
            gets = "✅" if (u["daily"] and u["hook"]) else "❌"
            print(f"  {u['id']:>3} {u['domain']:16}{u['name'][:12]:14}{u['role']:8}"
                  f"{u['watchlist']:5}{u['daily']:5}{u['hook']:8}  {gets}")

    if industry_cov:
        print(f"\n── 自选股行业映射覆盖率（US-158）──")
        for mkt, b in sorted(industry_cov.items()):
            if mkt.startswith("_"):
                continue
            pct = b["mapped"] * 100 // b["total"] if b["total"] else 0
            print(f"  {mkt:8} {b['mapped']:4}/{b['total']:4} ({pct:3}%)")
        by_src = industry_cov.get("_by_source") or {}
        if by_src:
            print(f"  全市场映射来源: {by_src}")
            if not by_src.get("em"):
                print("     🔴 em 为 0 —— Fly 上的东财源没通（不是新浪的结构性上限）")

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

    if survey_ft:
        print(f"\n── US-167 调研后续判定率（stock_prices 够不够密）──")
        print(f"  价格行 {survey_ft['price_rows']} / {survey_ft['price_codes']} 只 "
              f"= 每只约 {survey_ft['rows_per_code']} 行")
        print(f"  抽查 {survey_ft['stocks_with_surveys']} 只有调研数据的股票："
              f"已判定 {survey_ft['events_decided']} 个事件 · "
              f"待定 {survey_ft['events_pending']} 个 · "
              f"判定率 {survey_ft['decided_rate_pct']}%")
        print(f"  其中 {survey_ft['stocks_with_direction']} 只推得出方向（≥2 次专项调研的后续）")
        if survey_ft["decided_rate_pct"] < 30:
            print(f"  ⚠️  判定率偏低 —— 详情页那块「调研之后发生了什么」大面积说不出话")

    if ind_gap:
        print(f"\n── 自选里缺行业映射的 A股 是些什么（US-169）──")
        print(f"  按 asset_type: {ind_gap.get('by_asset_type')}")
        for code, name, at in ind_gap.get("sample", [])[:25]:
            print(f"    {code:10} {str(name)[:16]:18} {at}")

    if em_conv:
        print(f"\n── 东财行业映射收敛进度（US-158）──")
        print(f"  东财已映射 {em_conv.get('em_total')} 只 · 按日新增：")
        for d, n in em_conv.get("em_by_day", []):
            print(f"    {d}  {n} 只")
        if em_conv.get("error"): print(f"    {em_conv['error']}")

    if scan_jobs:
        print(f"\n── 最近的 scan 任务（东财映射搭的就是这趟车）──")
        for row in scan_jobs.get("recent", []):
            jid, jt, st, ca, err = row
            print(f"  #{jid} {jt} {st:8} {ca}")
            if err: print(f"      ⚠️  {err}")
        if scan_jobs.get("error"): print(f"  {scan_jobs['error']}")

    if wl_filter:
        print(f"\n── 自选页筛选：等级分布 + 筛选查询 ──")
        for g, n in (wl_filter.get("grades") or {}).items():
            print(f"    {g:4} {n:4} 只")
        if wl_filter.get("grades_error"):
            print(f"    等级分布查询失败: {wl_filter['grades_error']}")
        print(f"  筛选查询实跑: {wl_filter.get('filter_query')}")
        if str(wl_filter.get("filter_query", "")).startswith("FAILS"):
            print(f"  ⚠️  自选页所有筛选都是 500（前端静默失败，按钮点了没反应）")

    bad = [t for t in tables if t["status"] in ("EMPTY", "STALE", "ERROR", "MISSING")]
    print(f"\n共 {len(tables)} 张表，{len(bad)} 张需要关注\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
