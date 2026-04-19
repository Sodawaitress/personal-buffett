"""Stock, watchlist, price, fundamentals, and metadata queries."""

import json
from datetime import datetime, timezone

from radar_app.data.core import CN_TZ, get_conn


def upsert_stock(code, name, market, name_cn=None, exchange=None, sector=None, currency=None, asset_type=None):
    currency = currency or {"nz": "NZD", "cn": "CNY", "hk": "HKD", "us": "USD", "kr": "KRW"}.get(market, "USD")
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO stocks(code,name,name_cn,market,exchange,sector,currency,asset_type,last_fetched)
            VALUES(?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name, name_cn=COALESCE(excluded.name_cn,name_cn),
              market=excluded.market, exchange=COALESCE(excluded.exchange,exchange),
              sector=COALESCE(excluded.sector,sector),
              currency=excluded.currency,
              asset_type=COALESCE(excluded.asset_type,asset_type),
              last_fetched=excluded.last_fetched
        """,
            (code, name, name_cn, market, exchange, sector, currency, asset_type),
        )


def get_stock(code):
    with get_conn() as c:
        row = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        return dict(row) if row else None


def get_user_watchlist(user_id):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
            SELECT w.*, s.name, s.name_cn, s.market, s.currency, s.sector, s.asset_type
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE w.user_id=?
            ORDER BY w.added_at
        """,
                (user_id,),
            )
        ]


def add_user_stock(user_id, code, name, market, notes="", name_cn=None, exchange=None, sector=None, currency=None, asset_type=None):
    upsert_stock(code, name, market, name_cn=name_cn, exchange=exchange, sector=sector, currency=currency, asset_type=asset_type)
    with get_conn() as c:
        c.execute(
            """
            INSERT OR IGNORE INTO user_watchlist(user_id, stock_code, notes)
            VALUES(?,?,?)
        """,
            (user_id, code, notes),
        )


def remove_user_stock(user_id, code):
    with get_conn() as c:
        c.execute("DELETE FROM user_watchlist WHERE user_id=? AND stock_code=?", (user_id, code))


def all_watched_codes():
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT stock_code FROM user_watchlist")]


def get_all_cn_watchlist_stocks():
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT DISTINCT w.stock_code, COALESCE(s.name_cn, s.name, w.stock_code)
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE s.market = 'cn'
            ORDER BY w.stock_code
        """
        ).fetchall()
        return [(r[0], r[1]) for r in rows]


def get_users_with_daily_push():
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT u.id, u.email, u.display_name,
                   p.wecom_webhook, p.discord_webhook, p.bear_enabled
            FROM users u
            JOIN user_push_settings p ON p.user_id = u.id
            WHERE p.notify_daily = 1
        """
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_holdings(user_id):
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT stock_code FROM user_watchlist
            WHERE user_id=? AND status='holding'
        """,
            (user_id,),
        ).fetchall()
        return [r[0] for r in rows]


def get_user_watching(user_id):
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT stock_code FROM user_watchlist
            WHERE user_id=? AND status='watching'
        """,
            (user_id,),
        ).fetchall()
        return [r[0] for r in rows]


def set_stock_status(user_id, code, status, buy_price=None, buy_date=None, sell_price=None, sell_date=None):
    fields = {"status": status}
    if status == "holding":
        if buy_price:
            fields["buy_price"] = buy_price
        if buy_date:
            fields["buy_date"] = buy_date
    elif status == "sold":
        if sell_price:
            fields["sell_price"] = sell_price
        if sell_date:
            fields["sell_date"] = sell_date
    set_clause = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [user_id, code]
    with get_conn() as c:
        c.execute(f"UPDATE user_watchlist SET {set_clause} WHERE user_id=? AND stock_code=?", vals)


def _guess_market(code):
    import re

    if code.endswith(".NZ"):
        return "nz"
    if code.endswith(".HK"):
        return "hk"
    if code.endswith(".KS") or code.endswith(".KQ"):
        return "kr"
    if code.endswith(".AX"):
        return "au"
    if re.match(r"^\d{6}$", code):
        return "cn"
    return "us"


def upsert_price(code, price, change_pct=None, volume=None, market_cap=None, pe_ratio=None, pb_ratio=None):
    with get_conn() as c:
        c.execute(
            """
            INSERT OR IGNORE INTO stocks(code, name, market, currency)
            VALUES(?, ?, ?, 'CNY')
        """,
            (code, code, _guess_market(code)),
        )
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO stock_prices(code,price,change_pct,volume,market_cap,pe_ratio,pb_ratio)
            VALUES(?,?,?,?,?,?,?)
        """,
            (code, price, change_pct, volume, market_cap, pe_ratio, pb_ratio),
        )


def get_latest_price(code):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT * FROM stock_prices WHERE code=?
            ORDER BY fetched_at DESC LIMIT 1
        """,
            (code,),
        ).fetchone()
        return dict(row) if row else {}


def get_price_history(code, days=30):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
            SELECT * FROM stock_prices WHERE code=?
            ORDER BY fetched_at DESC LIMIT ?
        """,
                (code, days),
            )
        ]


def upsert_fund_flow(code, date, main_net, main_ratio):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO stocks(code,name,market,currency) VALUES(?,?,?,'CNY')", (code, code, _guess_market(code)))
        c.execute(
            """
            INSERT OR REPLACE INTO stock_fund_flow(code,date,main_net,main_ratio)
            VALUES(?,?,?,?)
        """,
            (code, date, main_net, main_ratio),
        )


def get_fund_flow(code):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT * FROM stock_fund_flow WHERE code=?
            ORDER BY date DESC LIMIT 1
        """,
            (code,),
        ).fetchone()
        return dict(row) if row else {}


def upsert_fundamentals(code, annual, pe_current=None, pe_percentile_5y=None, pb_current=None, pb_percentile_5y=None, signals=None):
    try:
        with get_conn() as c:
            c.execute("ALTER TABLE stock_fundamentals ADD COLUMN signals_json TEXT")
    except Exception:
        pass

    with get_conn() as c:
        c.execute(
            """
            INSERT INTO stock_fundamentals
                (code, annual_json, pe_current, pe_percentile_5y, pb_current, pb_percentile_5y,
                 signals_json, updated_at)
            VALUES (?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
                annual_json=excluded.annual_json,
                pe_current=excluded.pe_current,
                pe_percentile_5y=excluded.pe_percentile_5y,
                pb_current=excluded.pb_current,
                pb_percentile_5y=excluded.pb_percentile_5y,
                signals_json=COALESCE(excluded.signals_json, signals_json),
                updated_at=excluded.updated_at
        """,
            (
                code,
                json.dumps(annual, ensure_ascii=False),
                pe_current,
                pe_percentile_5y,
                pb_current,
                pb_percentile_5y,
                json.dumps(signals, ensure_ascii=False) if signals else None,
            ),
        )


def upsert_signals(code, signals: dict):
    try:
        with get_conn() as c:
            c.execute("ALTER TABLE stock_fundamentals ADD COLUMN signals_json TEXT")
    except Exception:
        pass
    with get_conn() as c:
        row = c.execute("SELECT signals_json FROM stock_fundamentals WHERE code=?", (code,)).fetchone()
        existing = {}
        if row and row[0]:
            try:
                existing = json.loads(row[0])
            except Exception:
                pass
        merged = {**existing, **signals}
        c.execute(
            """
            INSERT INTO stock_fundamentals(code, annual_json, signals_json, updated_at)
            VALUES (?, '[]', ?, datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
                signals_json=excluded.signals_json,
                updated_at=excluded.updated_at
        """,
            (code, json.dumps(merged, ensure_ascii=False)),
        )


def get_fundamentals(code):
    with get_conn() as c:
        row = c.execute("SELECT * FROM stock_fundamentals WHERE code=?", (code,)).fetchone()
        if not row:
            return {}
        data = dict(row)
        try:
            data["annual"] = json.loads(data.get("annual_json") or "[]")
        except Exception:
            data["annual"] = []
        try:
            data["signals"] = json.loads(data.get("signals_json") or "{}")
        except Exception:
            data["signals"] = {}
        return data


def get_fund_flow_history(code, days=30):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
            SELECT date, main_net, main_ratio FROM stock_fund_flow
            WHERE code=?
            ORDER BY date ASC LIMIT ?
        """,
                (code, days),
            )
        ]


def add_stock_event(code: str, event_type: str, event_date: str, summary: str, detail: dict = None, source: str = "manual"):
    with get_conn() as c:
        c.execute(
            "INSERT INTO stock_events(code, event_type, event_date, summary, detail_json, source) VALUES(?,?,?,?,?,?)",
            (code, event_type, event_date, summary, json.dumps(detail, ensure_ascii=False) if detail else None, source),
        )


def get_stock_events(code: str, limit: int = 20) -> list:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM stock_events WHERE code=? ORDER BY event_date DESC, id DESC LIMIT ?",
            (code, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stock_meta(code: str) -> dict:
    with get_conn() as c:
        row = c.execute("SELECT * FROM stock_meta WHERE code=?", (code,)).fetchone()
        return dict(row) if row else {}


def upsert_stock_meta(code: str, **fields):
    with get_conn() as c:
        existing = c.execute("SELECT manual_override FROM stock_meta WHERE code=?", (code,)).fetchone()
        if existing and existing["manual_override"] == 1:
            safe_fields = {k: v for k, v in fields.items() if k not in ("company_type", "st_status", "market_tier")}
            if not safe_fields:
                return
            fields = safe_fields

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fields["updated_at"] = now
        if "company_type" in fields or "st_status" in fields:
            fields["last_classified"] = now

        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
        c.execute(
            f"INSERT INTO stock_meta(code, {cols}) VALUES(?, {placeholders}) ON CONFLICT(code) DO UPDATE SET {updates}",
            (code, *fields.values()),
        )


def log_data_quality(code: str, field: str, value, flag: str, reason: str):
    with get_conn() as c:
        c.execute(
            "INSERT INTO data_quality_log(code, field, value, flag, reason) VALUES(?,?,?,?,?)",
            (code, field, str(value), flag, reason),
        )
