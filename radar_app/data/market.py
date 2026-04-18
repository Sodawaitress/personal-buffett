"""News and market snapshot queries."""

import hashlib
import json
from datetime import datetime, timedelta

from radar_app.data.core import CN_TZ, get_conn
from radar_app.data.stocks import _guess_market, all_watched_codes, get_latest_price, upsert_price


def save_north_bound(data: dict):
    with get_conn() as c:
        c.execute("DELETE FROM market_data WHERE data_type='north_bound'")
        c.execute("INSERT INTO market_data(data_type, payload) VALUES('north_bound', ?)", (json.dumps(data, ensure_ascii=False),))


def get_north_bound() -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT payload, fetched_at FROM market_data WHERE data_type='north_bound' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        try:
            data = json.loads(row["payload"])
            data["fetched_at"] = row["fetched_at"]
            return data
        except Exception:
            return {}


def upsert_stock_news(code, title, source, link, publish_time, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO stocks(code,name,market,currency) VALUES(?,?,?,'CNY')", (code, code, _guess_market(code)))
        c.execute(
            """
            INSERT OR IGNORE INTO stock_news(id,code,title,link,source,publish_time,fetched_date)
            VALUES(?,?,?,?,?,?,?)
        """,
            (nid, code, title, link, source, publish_time, fetched_date),
        )
    return nid


def get_stock_news(code, days=7):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """
            SELECT * FROM stock_news
            WHERE code=? AND fetched_date>=?
            ORDER BY publish_time DESC LIMIT 20
        """,
                (code, cutoff),
            )
        ]


def upsert_market_news(region, category, title, link, source, publish_time, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute(
            """
            INSERT OR IGNORE INTO market_news(id,region,category,title,link,source,publish_time,fetched_date)
            VALUES(?,?,?,?,?,?,?,?)
        """,
            (nid, region, category, title, link, source, publish_time, fetched_date),
        )


def get_market_news(region, category=None, days=3):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        if category:
            rows = c.execute(
                """
                SELECT * FROM market_news
                WHERE region=? AND category=? AND fetched_date>=?
                ORDER BY publish_time DESC LIMIT 10
            """,
                (region, category, cutoff),
            ).fetchall()
        else:
            rows = c.execute(
                """
            SELECT * FROM market_news
            WHERE region=? AND fetched_date>=?
            ORDER BY publish_time DESC LIMIT 20
        """,
                (region, cutoff),
            ).fetchall()
        return [dict(r) for r in rows]


def save_market_data(data_type, payload_dict):
    with get_conn() as c:
        c.execute("INSERT INTO market_data(data_type, payload) VALUES(?,?)", (data_type, json.dumps(payload_dict, ensure_ascii=False)))


def get_latest_market_data(data_type):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT * FROM market_data WHERE data_type=?
            ORDER BY fetched_at DESC LIMIT 1
        """,
            (data_type,),
        ).fetchone()
        if not row:
            return {}
        return json.loads(row["payload"])


def get_market_snapshot(market=None, date=None):
    types = ["nzx50", "fear_greed", "cny_usd", "cn_indices", "commodities"]
    result = {}
    for data_type in types:
        data = get_latest_market_data(data_type)
        if data:
            result[data_type] = data
    return {"data": result, "fetched_at": datetime.now(CN_TZ).isoformat()} if result else None


def upsert_news(code, title, source, link, publish_time, fetched_date):
    return upsert_stock_news(code, title, source, link, publish_time, fetched_date)


def get_news(code, days=3):
    return get_stock_news(code, days=days)


def upsert_intl_news(scope, title, label, link, source, fetched_date):
    return upsert_market_news("global", scope, title, link, source, "", fetched_date)


def upsert_market_snapshot(date, market, data_dict):
    for key, value in data_dict.items():
        save_market_data(key, value)


def upsert_quote(code, date, price, change_pct, amount):
    upsert_price(code, price, change_pct=change_pct, volume=amount)


def get_quotes(date=None):
    codes = all_watched_codes()
    return [get_latest_price(code) for code in codes if get_latest_price(code)]
