"""Analysis and report queries."""

from datetime import date, timedelta

from radar_app.data.core import get_conn
from radar_app.data.market import get_stock_news


def get_leaderboard(user_id, baseline_days=7):
    """US-120 股票擂台赛：用户自选股按最新 quant_score 降序排名 + 升降。

    返回 list[dict]：{rank, code, name, grade, score, score_change, rank_change}
      - score_change: 最新分 − 上一次分析的分（None=只有一条记录）
      - rank_change:  正=上升N名 / 负=下降N名 / 0=不变 / "NEW"=baseline无分 / None=无分(NR)
    无 quant_score 的股票排最后（NR，不占名次）。已卖出(sold)不计入。
    """
    cutoff = (date.today() - timedelta(days=baseline_days)).isoformat()
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT ar.code, ar.analysis_date, ar.quant_score, ar.grade,
                   COALESCE(s.name_cn, s.name, ar.code) AS name
            FROM analysis_results ar
            JOIN user_watchlist w ON w.stock_code = ar.code
            JOIN stocks s ON s.code = ar.code
            WHERE ar.period = 'daily'
              AND w.user_id = :uid AND w.removed_at IS NULL AND w.status != 'sold'
              AND ar.quant_score IS NOT NULL
            ORDER BY ar.code, ar.analysis_date DESC
            """,
            {"uid": user_id},
        ).fetchall()

    # 每只股票按日期倒序的记录归组
    by_code = {}
    for r in rows:
        by_code.setdefault(r["code"], []).append(r)

    scored = []       # 有分的：算当前分/变化/baseline分
    for code, recs in by_code.items():
        latest = recs[0]
        prev = recs[1] if len(recs) > 1 else None
        # baseline = cutoff 当天或之前最近一次分析
        baseline = next((x for x in recs if x["analysis_date"] <= cutoff), None)
        scored.append({
            "code": code,
            "name": latest["name"],
            "grade": latest["grade"],
            "score": latest["quant_score"],
            "score_change": (latest["quant_score"] - prev["quant_score"]) if prev else None,
            "_baseline_score": baseline["quant_score"] if baseline else None,
        })

    # 当前排名：分数降序（同分按 code 稳定）
    scored.sort(key=lambda x: (-x["score"], x["code"]))
    # baseline 排名：只排有 baseline 分的
    base_ranked = sorted(
        [x for x in scored if x["_baseline_score"] is not None],
        key=lambda x: (-x["_baseline_score"], x["code"]),
    )
    base_rank = {x["code"]: i + 1 for i, x in enumerate(base_ranked)}

    out = []
    for i, x in enumerate(scored):
        cur = i + 1
        if x["code"] in base_rank:
            rc = base_rank[x["code"]] - cur   # 正=名次前移(上升)
        else:
            rc = "NEW"
        out.append({
            "rank": cur, "code": x["code"], "name": x["name"],
            "grade": x["grade"], "score": x["score"],
            "score_change": x["score_change"], "rank_change": rc,
        })

    # 无分的股票（NR，排最后不占名次）
    with get_conn() as c:
        nr = c.execute(
            """
            SELECT w.stock_code AS code, COALESCE(s.name_cn, s.name, w.stock_code) AS name
            FROM user_watchlist w JOIN stocks s ON s.code = w.stock_code
            WHERE w.user_id = :uid AND w.removed_at IS NULL AND w.status != 'sold'
              AND w.stock_code NOT IN (
                  SELECT DISTINCT code FROM analysis_results
                  WHERE period='daily' AND quant_score IS NOT NULL
              )
            """,
            {"uid": user_id},
        ).fetchall()
    for r in nr:
        out.append({
            "rank": None, "code": r["code"], "name": r["name"],
            "grade": None, "score": None, "score_change": None, "rank_change": None,
        })

    return out


def save_analysis(code, period, analysis_date, **kwargs):
    params = {"code": code, "period": period, "analysis_date": analysis_date, **kwargs}
    cols = ", ".join(params.keys())
    placeholders = ", ".join(f":{k}" for k in params)
    # ON CONFLICT DO UPDATE preserves the row id and only updates changed columns.
    # INSERT OR REPLACE would delete-then-insert, losing the auto-increment id.
    update_set = ", ".join(
        f"{k}=excluded.{k}" for k in params if k not in ("code", "period", "analysis_date")
    )
    sql = f"INSERT INTO analysis_results({cols}) VALUES({placeholders})"
    if update_set:
        sql += f" ON CONFLICT(code, period, analysis_date) DO UPDATE SET {update_set}"
    with get_conn() as c:
        c.execute(sql, params)


def get_latest_analysis(code, period="daily"):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT * FROM analysis_results
            WHERE code=:code AND period=:period
            ORDER BY analysis_date DESC, id DESC LIMIT 1
            """,
            {"code": code, "period": period},
        ).fetchone()
        return dict(row) if row else {}


def get_analysis_history(code, period="daily", limit=10):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
                SELECT * FROM analysis_results
                WHERE code=:code AND period=:period
                ORDER BY analysis_date DESC LIMIT :limit
                """,
                {"code": code, "period": period, "limit": limit},
            )
        ]


def get_news_range(code, days=7):
    return get_stock_news(code, days=days)


def save_report(date, html, md, period="daily"):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO reports(analysis_date,period,html,md) VALUES(:date,:period,:html,:md)
            ON CONFLICT(analysis_date,period) DO UPDATE SET html=excluded.html, md=excluded.md
            """,
            {"date": date, "period": period, "html": html, "md": md},
        )


def get_report(date=None, period="daily"):
    with get_conn() as c:
        if date:
            row = c.execute(
                "SELECT * FROM reports WHERE analysis_date=:date AND period=:period",
                {"date": date, "period": period},
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM reports WHERE period=:period ORDER BY analysis_date DESC, id DESC LIMIT 1",
                {"period": period},
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["date"] = data.get("analysis_date")
        return data


def list_reports(limit=30, period=None):
    with get_conn() as c:
        if period:
            rows = c.execute(
                """
                SELECT analysis_date as date, period, created_at FROM reports
                WHERE period=:period ORDER BY analysis_date DESC LIMIT :limit
                """,
                {"period": period, "limit": limit},
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT analysis_date as date, period, created_at FROM reports
                ORDER BY analysis_date DESC LIMIT :limit
                """,
                {"limit": limit},
            ).fetchall()
        return [dict(r) for r in rows]


def get_accuracy_stats():
    threshold = 3.0
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT ar.code, s.name, ar.analysis_date, ar.conclusion, ar.grade,
                   ar.label_7d_return, ar.label_30d_return, ar.reasoning
            FROM analysis_results ar
            JOIN stocks s ON s.code = ar.code
            WHERE ar.period='daily'
              AND (ar.label_7d_return IS NOT NULL OR ar.label_30d_return IS NOT NULL)
            ORDER BY ar.analysis_date DESC
            """
        ).fetchall()

    def verdict(conclusion, actual_return):
        if actual_return is None:
            return None
        if conclusion in ("买入",):
            if actual_return > threshold:
                return "correct"
            if actual_return < -threshold:
                return "wrong"
            return "neutral"
        if conclusion in ("减持", "卖出"):
            if actual_return < -threshold:
                return "correct"
            if actual_return > threshold:
                return "wrong"
            return "neutral"
        if abs(actual_return) <= threshold:
            return "correct"
        return "neutral"

    by_type = {}
    recent_wrong = []
    for row in rows:
        data = dict(row)
        for horizon, col in [("7d", "label_7d_return"), ("30d", "label_30d_return")]:
            ret = data.get(col)
            key = f"{data['conclusion']}_{horizon}"
            if key not in by_type:
                by_type[key] = {"conclusion": data["conclusion"], "horizon": horizon, "total": 0, "correct": 0, "wrong": 0, "neutral": 0}
            value = verdict(data["conclusion"], ret)
            if value:
                by_type[key]["total"] += 1
                by_type[key][value] += 1
                if value == "wrong" and horizon == "7d":
                    recent_wrong.append(
                        {
                            "code": data["code"],
                            "name": data["name"],
                            "date": data["analysis_date"],
                            "conclusion": data["conclusion"],
                            "return_7d": data["label_7d_return"],
                            "reasoning": (data["reasoning"] or "")[:80],
                        }
                    )

    stats = []
    for key, stat in by_type.items():
        accuracy = round(stat["correct"] / stat["total"] * 100) if stat["total"] > 0 else None
        stats.append({**stat, "accuracy_pct": accuracy, "key": key})
    stats.sort(key=lambda item: (item["conclusion"], item["horizon"]))

    return {"by_type": stats, "recent_wrong": recent_wrong[:10], "total_labelled": len(rows)}
