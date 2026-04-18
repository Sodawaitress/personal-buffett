"""Portfolio and performance queries."""

from datetime import datetime, timedelta, timezone

from radar_app.data.core import get_conn


def update_stock_status(user_id, code, status, buy_date=None, buy_price=None, sell_date=None, sell_price=None, entry_grade=None):
    fields = {"status": status}
    if status == "holding":
        if buy_date:
            fields["buy_date"] = buy_date
        if buy_price:
            fields["buy_price"] = buy_price
        if entry_grade:
            fields["entry_grade"] = entry_grade
        fields["sell_date"] = None
        fields["sell_price"] = None
    elif status == "sold":
        if sell_date:
            fields["sell_date"] = sell_date
        if sell_price:
            fields["sell_price"] = sell_price
    elif status == "watching":
        fields.update({"buy_date": None, "buy_price": None, "sell_date": None, "sell_price": None, "entry_grade": None})
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as c:
        c.execute(f"UPDATE user_watchlist SET {set_clause} WHERE user_id=? AND stock_code=?", list(fields.values()) + [user_id, code])


def get_performance_data(user_id):
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT w.stock_code AS code, s.name, s.market, w.status,
                   w.buy_date, w.buy_price, w.sell_date, w.sell_price,
                   w.entry_grade, w.added_at
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE w.user_id=? AND w.status IN ('holding','sold')
            ORDER BY w.buy_date DESC NULLS LAST
        """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_portfolio_brief(user_id, date=None):
    with get_conn() as c:
        if date:
            row = c.execute("SELECT * FROM portfolio_analysis WHERE user_id=? AND analysis_date=?", (user_id, date)).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM portfolio_analysis WHERE user_id=? ORDER BY analysis_date DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None


def save_portfolio_brief(user_id, analysis_date, macro_headline, buffett_summary):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO portfolio_analysis(user_id, analysis_date, macro_headline, buffett_summary)
            VALUES(?,?,?,?)
            ON CONFLICT(user_id, analysis_date)
            DO UPDATE SET macro_headline=excluded.macro_headline,
                          buffett_summary=excluded.buffett_summary,
                          created_at=datetime('now')
        """,
            (user_id, analysis_date, macro_headline, buffett_summary),
        )
