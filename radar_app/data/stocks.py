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
            VALUES(:code,:name,:name_cn,:market,:exchange,:sector,:currency,:asset_type,CURRENT_TIMESTAMP)
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name, name_cn=COALESCE(excluded.name_cn,name_cn),
              market=excluded.market, exchange=COALESCE(excluded.exchange,exchange),
              sector=COALESCE(excluded.sector,sector),
              currency=excluded.currency,
              asset_type=COALESCE(excluded.asset_type,asset_type),
              last_fetched=excluded.last_fetched
            """,
            {"code": code, "name": name, "name_cn": name_cn, "market": market,
             "exchange": exchange, "sector": sector, "currency": currency, "asset_type": asset_type},
        )


def get_stock(code):
    with get_conn() as c:
        row = c.execute("SELECT * FROM stocks WHERE code=:code", {"code": code}).fetchone()
        return dict(row) if row else None


def get_user_watchlist(user_id, status=None, market=None, asset_type=None):
    query = """
        SELECT w.*, s.name, s.name_cn, s.market, s.currency, s.sector, s.asset_type
        FROM user_watchlist w
        JOIN stocks s ON s.code = w.stock_code
        WHERE w.user_id = :user_id AND w.removed_at IS NULL
    """
    params = {"user_id": user_id}
    if status:
        query += " AND w.status = :status"
        params["status"] = status
    if market:
        query += " AND s.market = :market"
        params["market"] = market
    if asset_type:
        query += " AND s.asset_type = :asset_type"
        params["asset_type"] = asset_type
    query += " ORDER BY w.added_at"
    with get_conn() as c:
        return [dict(r) for r in c.execute(query, params)]


def add_user_stock(user_id, code, name, market, notes="", name_cn=None, exchange=None, sector=None, currency=None, asset_type=None):
    upsert_stock(code, name, market, name_cn=name_cn, exchange=exchange, sector=sector, currency=currency, asset_type=asset_type)
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO user_watchlist(user_id, stock_code, notes)
            VALUES(:uid,:code,:notes)
            ON CONFLICT(user_id, stock_code) DO NOTHING
            """,
            {"uid": user_id, "code": code, "notes": notes},
        )


def remove_user_stock(user_id, code):
    with get_conn() as c:
        c.execute(
            "UPDATE user_watchlist SET removed_at=CURRENT_TIMESTAMP WHERE user_id=:uid AND stock_code=:code AND removed_at IS NULL",
            {"uid": user_id, "code": code},
        )


def all_watched_codes():
    with get_conn() as c:
        return [r["stock_code"] for r in c.execute("SELECT DISTINCT stock_code FROM user_watchlist WHERE removed_at IS NULL")]


def get_users_watching_code(code: str) -> list[int]:
    """返回所有 watching/holding 该股票的 user_id 列表（未删除）。"""
    with get_conn() as c:
        rows = c.execute(
            "SELECT user_id FROM user_watchlist WHERE stock_code=:code AND removed_at IS NULL",
            {"code": code},
        ).fetchall()
        return [r["user_id"] for r in rows]


def get_all_cn_watchlist_stocks():
    """所有用户的A股自选股（含休眠用户）。"""
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT DISTINCT w.stock_code,
                   COALESCE(s.name_cn, s.name, w.stock_code) AS display_name
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE s.market = 'cn' AND w.removed_at IS NULL
            ORDER BY w.stock_code
            """
        ).fetchall()
        return [(r["stock_code"], r["display_name"]) for r in rows]


def get_active_watchlist_stocks():
    """只返回开启了 daily push 的用户的A股自选股（pipeline 抓取范围）。"""
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT DISTINCT w.stock_code,
                   COALESCE(s.name_cn, s.name, w.stock_code) AS display_name
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            JOIN user_push_settings p ON p.user_id = w.user_id
            WHERE s.market = 'cn'
              AND p.notify_daily = 1
              AND w.removed_at IS NULL
            ORDER BY w.stock_code
            """
        ).fetchall()
        return [(r["stock_code"], r["display_name"]) for r in rows]


def is_data_fresh(code: str, data_type: str, max_hours: float = 8.0) -> bool:
    """检查某支股票的某类数据是否仍在新鲜期内。"""
    now = datetime.now(CN_TZ)
    with get_conn() as c:
        if data_type == "price":
            row = c.execute(
                "SELECT fetched_at FROM stock_prices WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
                {"code": code},
            ).fetchone()
            if not row:
                return False
            ts = row["fetched_at"]
            last = datetime.fromisoformat(ts).replace(tzinfo=CN_TZ) if "+" not in ts else datetime.fromisoformat(ts)
            return (now - last).total_seconds() < max_hours * 3600

        if data_type == "news":
            row = c.execute(
                "SELECT publish_time FROM stock_news WHERE code=:code ORDER BY publish_time DESC LIMIT 1",
                {"code": code},
            ).fetchone()
            if not row:
                return False
            try:
                last = datetime.fromisoformat(row["publish_time"]).replace(tzinfo=CN_TZ)
                return (now - last).total_seconds() < max_hours * 3600
            except Exception:
                return False

        if data_type == "fund_flow":
            today = now.strftime("%Y-%m-%d")
            row = c.execute(
                "SELECT 1 FROM stock_fund_flow WHERE code=:code AND date=:today",
                {"code": code, "today": today},
            ).fetchone()
            return row is not None

    return False


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
            "SELECT stock_code FROM user_watchlist WHERE user_id=:uid AND status='holding' AND removed_at IS NULL",
            {"uid": user_id},
        ).fetchall()
        return [r["stock_code"] for r in rows]


def get_user_watching(user_id):
    with get_conn() as c:
        rows = c.execute(
            "SELECT stock_code FROM user_watchlist WHERE user_id=:uid AND status='watching' AND removed_at IS NULL",
            {"uid": user_id},
        ).fetchall()
        return [r["stock_code"] for r in rows]


_WATCHLIST_UPDATABLE = {"status", "buy_price", "buy_date", "sell_price", "sell_date"}


def set_stock_status(user_id, code, status, buy_price=None, buy_date=None, sell_price=None, sell_date=None):
    fields = {"status": status}
    if status == "holding":
        if buy_price is not None:
            fields["buy_price"] = buy_price
        if buy_date:
            fields["buy_date"] = buy_date
    elif status == "sold":
        if sell_price is not None:
            fields["sell_price"] = sell_price
        if sell_date:
            fields["sell_date"] = sell_date
    unknown = set(fields) - _WATCHLIST_UPDATABLE
    if unknown:
        raise ValueError(f"set_stock_status: unexpected fields {unknown}")
    set_clause = ", ".join(f"{k}=:{k}" for k in fields)
    params = {**fields, "user_id": user_id, "code": code}
    with get_conn() as c:
        c.execute(
            f"UPDATE user_watchlist SET {set_clause} WHERE user_id=:user_id AND stock_code=:code",
            params,
        )


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
    # Both inserts in one transaction — if the price insert fails, the stock stub is also rolled back.
    with get_conn() as c:
        c.execute(
            "INSERT INTO stocks(code,name,market,currency) VALUES(:code,:code,:market,'CNY') ON CONFLICT DO NOTHING",
            {"code": code, "market": _guess_market(code)},
        )
        c.execute(
            """
            INSERT INTO stock_prices(code,price,change_pct,volume,market_cap,pe_ratio,pb_ratio)
            VALUES(:code,:price,:change_pct,:volume,:market_cap,:pe_ratio,:pb_ratio)
            """,
            {"code": code, "price": price, "change_pct": change_pct, "volume": volume,
             "market_cap": market_cap, "pe_ratio": pe_ratio, "pb_ratio": pb_ratio},
        )


def get_latest_price(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM stock_prices WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
            {"code": code},
        ).fetchone()
        return dict(row) if row else {}


def get_price_history(code, days=30):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM stock_prices WHERE code=:code ORDER BY fetched_at DESC LIMIT :days",
                {"code": code, "days": days},
            )
        ]


def get_price_52week(code):
    """Return {high, low} over the last 365 price rows."""
    with get_conn() as c:
        row = c.execute(
            """SELECT MAX(price) AS high, MIN(price) AS low
               FROM (SELECT price FROM stock_prices WHERE code=:code
                     ORDER BY fetched_at DESC LIMIT 365)""",
            {"code": code},
        ).fetchone()
        if not row:
            return {}
        return {"high": row["high"], "low": row["low"]}


def get_watchlist_entry(user_id, code):
    """Return the single watchlist row for user+code (with buy_price, buy_date, status)."""
    with get_conn() as c:
        row = c.execute(
            """SELECT w.*, s.name, s.market, s.currency
               FROM user_watchlist w
               JOIN stocks s ON s.code = w.stock_code
               WHERE w.user_id=:uid AND w.stock_code=:code AND w.removed_at IS NULL
               ORDER BY w.id DESC LIMIT 1""",
            {"uid": user_id, "code": code},
        ).fetchone()
        return dict(row) if row else None


def save_analyst_consensus(code, data: dict):
    with get_conn() as c:
        c.execute(
            """INSERT INTO analyst_consensus(code, fetched_at, data_json)
               VALUES(:code, datetime('now'), :data)
               ON CONFLICT(code) DO UPDATE SET fetched_at=excluded.fetched_at, data_json=excluded.data_json""",
            {"code": code, "data": json.dumps(data, ensure_ascii=False)},
        )


def get_analyst_consensus(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT fetched_at, data_json FROM analyst_consensus WHERE code=:code",
            {"code": code},
        ).fetchone()
        if not row:
            return None
        try:
            d = json.loads(row["data_json"])
            d["fetched_at"] = row["fetched_at"]
            return d
        except Exception:
            return None


def save_industry_signal(industry_key: str, data: dict):
    with get_conn() as c:
        c.execute(
            """INSERT INTO industry_signals(industry_key, fetched_at, signal_json)
               VALUES(:k, datetime('now'), :data)
               ON CONFLICT(industry_key) DO UPDATE SET fetched_at=excluded.fetched_at, signal_json=excluded.signal_json""",
            {"k": industry_key, "data": json.dumps(data, ensure_ascii=False)},
        )


def get_industry_signal(industry_key: str):
    with get_conn() as c:
        row = c.execute(
            "SELECT fetched_at, signal_json FROM industry_signals WHERE industry_key=:k",
            {"k": industry_key},
        ).fetchone()
        if not row:
            return None
        try:
            d = json.loads(row["signal_json"])
            d["fetched_at"] = row["fetched_at"]
            return d
        except Exception:
            return None


def upsert_fund_flow(code, date, main_net, main_ratio):
    # Both inserts in one transaction.
    with get_conn() as c:
        c.execute(
            "INSERT INTO stocks(code,name,market,currency) VALUES(:code,:code,:market,'CNY') ON CONFLICT DO NOTHING",
            {"code": code, "market": _guess_market(code)},
        )
        c.execute(
            """
            INSERT INTO stock_fund_flow(code,date,main_net,main_ratio)
            VALUES(:code,:date,:main_net,:main_ratio)
            ON CONFLICT(code,date) DO UPDATE SET main_net=excluded.main_net, main_ratio=excluded.main_ratio
            """,
            {"code": code, "date": date, "main_net": main_net, "main_ratio": main_ratio},
        )


def get_fund_flow(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM stock_fund_flow WHERE code=:code ORDER BY date DESC LIMIT 1",
            {"code": code},
        ).fetchone()
        return dict(row) if row else {}


def upsert_fundamentals(code, annual, pe_current=None, pe_percentile_5y=None, pb_current=None, pb_percentile_5y=None, signals=None):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO stock_fundamentals
                (code, annual_json, pe_current, pe_percentile_5y, pb_current, pb_percentile_5y,
                 signals_json, updated_at)
            VALUES (:code,:annual,:pe,:pe_pct,:pb,:pb_pct,:signals,CURRENT_TIMESTAMP)
            ON CONFLICT(code) DO UPDATE SET
                annual_json=excluded.annual_json,
                pe_current=excluded.pe_current,
                pe_percentile_5y=excluded.pe_percentile_5y,
                pb_current=excluded.pb_current,
                pb_percentile_5y=excluded.pb_percentile_5y,
                signals_json=COALESCE(excluded.signals_json, signals_json),
                updated_at=excluded.updated_at
            """,
            {
                "code": code,
                "annual": json.dumps(annual, ensure_ascii=False),
                "pe": pe_current,
                "pe_pct": pe_percentile_5y,
                "pb": pb_current,
                "pb_pct": pb_percentile_5y,
                "signals": json.dumps(signals, ensure_ascii=False) if signals else None,
            },
        )


def upsert_signals(code, signals: dict):
    with get_conn() as c:
        row = c.execute(
            "SELECT signals_json FROM stock_fundamentals WHERE code=:code", {"code": code}
        ).fetchone()
        existing = {}
        if row and row["signals_json"]:
            try:
                existing = json.loads(row["signals_json"])
            except Exception:
                pass
        merged = {**existing, **signals}
        c.execute(
            """
            INSERT INTO stock_fundamentals(code, annual_json, signals_json, updated_at)
            VALUES (:code, '[]', :signals, CURRENT_TIMESTAMP)
            ON CONFLICT(code) DO UPDATE SET
                signals_json=excluded.signals_json,
                updated_at=excluded.updated_at
            """,
            {"code": code, "signals": json.dumps(merged, ensure_ascii=False)},
        )


def get_fundamentals(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM stock_fundamentals WHERE code=:code", {"code": code}
        ).fetchone()
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
                WHERE code=:code ORDER BY date ASC LIMIT :days
                """,
                {"code": code, "days": days},
            )
        ]


def add_stock_event(code: str, event_type: str, event_date: str, summary: str, detail: dict = None, source: str = "manual"):
    with get_conn() as c:
        c.execute(
            "INSERT INTO stock_events(code, event_type, event_date, summary, detail_json, source) "
            "VALUES(:code,:event_type,:event_date,:summary,:detail,:source)",
            {
                "code": code, "event_type": event_type, "event_date": event_date,
                "summary": summary,
                "detail": json.dumps(detail, ensure_ascii=False) if detail else None,
                "source": source,
            },
        )


def get_stock_events(code: str, limit: int = 20) -> list:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM stock_events WHERE code=:code ORDER BY event_date DESC, id DESC LIMIT :limit",
            {"code": code, "limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def get_upcoming_events_for_user(user_id: int, days_ahead: int = 7) -> list:
    """Return events in the next days_ahead days for a user's watchlist stocks."""
    from datetime import date, timedelta
    today = date.today().strftime("%Y-%m-%d")
    horizon = (date.today() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT e.code,
                   COALESCE(s.name_cn, s.name, e.code) AS display_name,
                   e.event_type, e.event_date, e.summary, e.detail_json
            FROM stock_events e
            JOIN user_watchlist w ON w.stock_code = e.code
            JOIN stocks s ON s.code = e.code
            WHERE w.user_id = :uid
              AND w.removed_at IS NULL
              AND e.event_date >= :today
              AND e.event_date <= :horizon
            ORDER BY e.event_date ASC, e.id DESC
            """,
            {"uid": user_id, "today": today, "horizon": horizon},
        ).fetchall()
    result = []
    seen = set()
    for r in rows:
        d = dict(r)
        key = (d["code"], d["event_date"], d["summary"])
        if key in seen:
            continue
        seen.add(key)
        d["days_until"] = (date.fromisoformat(d["event_date"]) - date.today()).days
        result.append(d)
    return result


def get_stock_meta(code: str) -> dict:
    with get_conn() as c:
        row = c.execute("SELECT * FROM stock_meta WHERE code=:code", {"code": code}).fetchone()
        return dict(row) if row else {}


def upsert_stock_meta(code: str, **fields):
    with get_conn() as c:
        existing = c.execute(
            "SELECT manual_override FROM stock_meta WHERE code=:code", {"code": code}
        ).fetchone()
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
        placeholders = ", ".join(f":{k}" for k in fields)
        updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
        c.execute(
            f"INSERT INTO stock_meta(code, {cols}) VALUES(:code, {placeholders}) "
            f"ON CONFLICT(code) DO UPDATE SET {updates}",
            {"code": code, **fields},
        )


def log_data_quality(code: str, field: str, value, flag: str, reason: str):
    with get_conn() as c:
        c.execute(
            "INSERT INTO data_quality_log(code, field, value, flag, reason) VALUES(:code,:field,:value,:flag,:reason)",
            {"code": code, "field": field, "value": str(value), "flag": flag, "reason": reason},
        )


def get_news_sentiment_map(codes: list) -> dict:
    """Batch query: avg sentiment for each code over the last 7 days.

    Returns {code: float} only for codes that have ≥3 news items with
    a non-null sentiment score. Codes with insufficient data are absent.
    One query regardless of how many codes are passed.
    """
    if not codes:
        return {}
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {f"c{i}": c for i, c in enumerate(codes)}
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT code, AVG(sentiment) AS avg_s
            FROM stock_news
            WHERE code IN ({placeholders})
              AND fetched_date >= date('now', '-7 days')
              AND sentiment IS NOT NULL
            GROUP BY code
            HAVING COUNT(*) >= 3
            """,
            params,
        ).fetchall()
    return {r["code"]: round(r["avg_s"], 3) for r in rows}
