"""Analysis and report queries."""

from radar_app.data.core import get_conn
from radar_app.data.market import get_stock_news


def save_analysis(code, period, analysis_date, **kwargs):
    new_cols = [
        "ALTER TABLE analysis_results ADD COLUMN trade_block TEXT",
        "ALTER TABLE analysis_results ADD COLUMN quant_score INTEGER",
        "ALTER TABLE analysis_results ADD COLUMN quant_components TEXT",
    ]
    with get_conn() as c:
        for sql in new_cols:
            try:
                c.execute(sql)
            except Exception:
                pass
    cols = ["code", "period", "analysis_date"] + list(kwargs.keys())
    vals = [code, period, analysis_date] + list(kwargs.values())
    placeholders = ",".join(["?"] * len(vals))
    with get_conn() as c:
        c.execute(f"INSERT OR REPLACE INTO analysis_results({','.join(cols)}) VALUES({placeholders})", vals)


def get_latest_analysis(code, period="daily"):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT * FROM analysis_results
            WHERE code=? AND period=?
            ORDER BY analysis_date DESC, id DESC LIMIT 1
        """,
            (code, period),
        ).fetchone()
        return dict(row) if row else {}


def get_analysis_history(code, period="daily", limit=10):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
            SELECT * FROM analysis_results
            WHERE code=? AND period=?
            ORDER BY analysis_date DESC LIMIT ?
        """,
                (code, period, limit),
            )
        ]


def get_news_range(code, days=7):
    return get_stock_news(code, days=days)


def save_report(date, html, md, period="daily"):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO reports(analysis_date,period,html,md) VALUES(?,?,?,?)
            ON CONFLICT(analysis_date,period) DO UPDATE SET html=excluded.html, md=excluded.md
        """,
            (date, period, html, md),
        )


def get_report(date=None, period="daily"):
    with get_conn() as c:
        if date:
            row = c.execute("SELECT * FROM reports WHERE analysis_date=? AND period=?", (date, period)).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM reports WHERE period=? ORDER BY analysis_date DESC, id DESC LIMIT 1",
                (period,),
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
                WHERE period=? ORDER BY analysis_date DESC LIMIT ?
            """,
                (period, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT analysis_date as date, period, created_at FROM reports
                ORDER BY analysis_date DESC LIMIT ?
            """,
                (limit,),
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
