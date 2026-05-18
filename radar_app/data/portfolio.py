"""Portfolio and performance queries."""

from radar_app.data.core import get_conn


def update_stock_status(user_id, code, status, buy_date=None, buy_price=None, sell_date=None, sell_price=None, entry_grade=None):
    fields = {"status": status}
    if status == "holding":
        if buy_date:
            fields["buy_date"] = buy_date
        if buy_price is not None:
            fields["buy_price"] = buy_price
        if entry_grade:
            fields["entry_grade"] = entry_grade
        fields["sell_date"] = None
        fields["sell_price"] = None
    elif status == "sold":
        if sell_date:
            fields["sell_date"] = sell_date
        if sell_price is not None:
            fields["sell_price"] = sell_price
    elif status == "watching":
        fields.update({"buy_date": None, "buy_price": None, "sell_date": None, "sell_price": None, "entry_grade": None})
    set_clause = ", ".join(f"{k}=:{k}" for k in fields)
    params = {**fields, "user_id": user_id, "code": code}
    with get_conn() as c:
        c.execute(
            f"UPDATE user_watchlist SET {set_clause} WHERE user_id=:user_id AND stock_code=:code",
            params,
        )


def get_performance_data(user_id):
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT w.stock_code AS code, s.name, s.market, w.status,
                   w.buy_date, w.buy_price, w.sell_date, w.sell_price,
                   w.entry_grade, w.added_at,
                   COALESCE(sm.company_type, 'other') AS company_type
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            LEFT JOIN stock_meta sm ON sm.code = w.stock_code
            WHERE w.user_id=:uid AND w.status IN ('holding','sold')
            ORDER BY w.buy_date DESC NULLS LAST
            """,
            {"uid": user_id},
        ).fetchall()
    return [dict(r) for r in rows]


def get_portfolio_brief(user_id, date=None):
    with get_conn() as c:
        if date:
            row = c.execute(
                "SELECT * FROM portfolio_analysis WHERE user_id=:uid AND analysis_date=:date",
                {"uid": user_id, "date": date},
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM portfolio_analysis WHERE user_id=:uid ORDER BY analysis_date DESC, id DESC LIMIT 1",
                {"uid": user_id},
            ).fetchone()
        return dict(row) if row else None


def save_portfolio_brief(user_id, analysis_date, macro_headline, buffett_summary):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO portfolio_analysis(user_id, analysis_date, macro_headline, buffett_summary)
            VALUES(:uid,:date,:macro,:buffett)
            ON CONFLICT(user_id, analysis_date)
            DO UPDATE SET macro_headline=excluded.macro_headline,
                          buffett_summary=excluded.buffett_summary,
                          created_at=CURRENT_TIMESTAMP
            """,
            {"uid": user_id, "date": analysis_date, "macro": macro_headline, "buffett": buffett_summary},
        )
