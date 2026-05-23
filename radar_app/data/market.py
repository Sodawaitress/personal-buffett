"""News and market snapshot queries."""

import hashlib
import json
from datetime import datetime, timedelta

from radar_app.data.core import CN_TZ, get_conn
from radar_app.data.stocks import _guess_market, all_watched_codes, get_latest_price, upsert_price


def save_north_bound(data: dict):
    with get_conn() as c:
        c.execute("DELETE FROM market_data WHERE data_type='north_bound'")
        c.execute(
            "INSERT INTO market_data(data_type, payload) VALUES('north_bound', :payload)",
            {"payload": json.dumps(data, ensure_ascii=False)},
        )


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
        c.execute(
            "INSERT INTO stocks(code,name,market,currency) VALUES(:code,:code,:market,'CNY') ON CONFLICT DO NOTHING",
            {"code": code, "market": _guess_market(code)},
        )
        c.execute(
            """
            INSERT INTO stock_news(id,code,title,link,source,publish_time,fetched_date)
            VALUES(:id,:code,:title,:link,:source,:publish_time,:fetched_date)
            ON CONFLICT DO NOTHING
            """,
            {"id": nid, "code": code, "title": title, "link": link, "source": source,
             "publish_time": publish_time, "fetched_date": fetched_date},
        )
    return nid


def _sentiment_label(val) -> str:
    """Convert stored REAL sentiment (-1.0/0.0/1.0) to display label."""
    if val is None:
        return ""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if v > 0.3:
        return "positive"
    if v < -0.3:
        return "negative"
    return "neutral"


def get_stock_news(code, days=7):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT * FROM stock_news
            WHERE code=:code AND fetched_date>=:cutoff
            ORDER BY publish_time DESC LIMIT 20
            """,
            {"code": code, "cutoff": cutoff},
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["sentiment"] = _sentiment_label(d.get("sentiment"))
        result.append(d)
    return result


def upsert_market_news(region, category, title, link, source, publish_time, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO market_news(id,region,category,title,link,source,publish_time,fetched_date)
            VALUES(:id,:region,:category,:title,:link,:source,:publish_time,:fetched_date)
            ON CONFLICT DO NOTHING
            """,
            {"id": nid, "region": region, "category": category, "title": title, "link": link,
             "source": source, "publish_time": publish_time, "fetched_date": fetched_date},
        )


def get_market_news(region, category=None, days=3):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        if category:
            rows = c.execute(
                """
                SELECT * FROM market_news
                WHERE region=:region AND category=:category AND fetched_date>=:cutoff
                ORDER BY publish_time DESC LIMIT 10
                """,
                {"region": region, "category": category, "cutoff": cutoff},
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT * FROM market_news
                WHERE region=:region AND fetched_date>=:cutoff
                ORDER BY publish_time DESC LIMIT 20
                """,
                {"region": region, "cutoff": cutoff},
            ).fetchall()
        return [dict(r) for r in rows]


def save_market_data(data_type, payload_dict):
    with get_conn() as c:
        c.execute(
            "INSERT INTO market_data(data_type, payload) VALUES(:type,:payload)",
            {"type": data_type, "payload": json.dumps(payload_dict, ensure_ascii=False)},
        )


def get_latest_market_data(data_type):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM market_data WHERE data_type=:type ORDER BY fetched_at DESC LIMIT 1",
            {"type": data_type},
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
    prices = [get_latest_price(code) for code in codes]
    return [p for p in prices if p]


# ── 机构雷达 DB 层 ────────────────────────────────────

def upsert_northbound_hist(date: str, total_net: float):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO northbound_history(date, total_net) VALUES(:date,:total_net)
            ON CONFLICT(date) DO UPDATE SET total_net=excluded.total_net
            """,
            {"date": date, "total_net": total_net},
        )


def get_northbound_hist(days: int = 10) -> list:
    with get_conn() as c:
        rows = c.execute(
            "SELECT date, total_net FROM northbound_history ORDER BY date DESC LIMIT :days",
            {"days": days},
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_block_trade(code: str, trade_date: str, premium_pct: float, amount_mn: float):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO block_trades(code, trade_date, premium_pct, amount_mn)
            VALUES(:code,:trade_date,:premium_pct,:amount_mn)
            ON CONFLICT DO NOTHING
            """,
            {"code": code, "trade_date": trade_date, "premium_pct": premium_pct, "amount_mn": amount_mn},
        )


def get_block_trades(code: str, days: int = 7) -> list:
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM block_trades WHERE code=:code AND trade_date >= :cutoff ORDER BY trade_date DESC",
            {"code": code, "cutoff": cutoff},
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_insider_change(code: str, holder_name: str, role: str,
                           change_type: str, shares: float, avg_price: float,
                           change_date: str):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO insider_changes(code, holder_name, role, change_type, shares, avg_price, change_date)
            VALUES(:code,:holder_name,:role,:change_type,:shares,:avg_price,:change_date)
            ON CONFLICT DO NOTHING
            """,
            {"code": code, "holder_name": holder_name, "role": role, "change_type": change_type,
             "shares": shares, "avg_price": avg_price, "change_date": change_date},
        )


def get_insider_changes(code: str, days: int = 30) -> list:
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM insider_changes WHERE code=:code AND change_date >= :cutoff ORDER BY change_date DESC",
            {"code": code, "cutoff": cutoff},
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_inst_quarterly(code: str, quarter: str, shareholder_cnt: int, sh_pct_change: float):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO inst_quarterly(code, quarter, shareholder_cnt, sh_pct_change)
            VALUES(:code,:quarter,:shareholder_cnt,:sh_pct_change)
            ON CONFLICT(code, quarter) DO UPDATE SET
                shareholder_cnt=excluded.shareholder_cnt,
                sh_pct_change=excluded.sh_pct_change
            """,
            {"code": code, "quarter": quarter, "shareholder_cnt": shareholder_cnt, "sh_pct_change": sh_pct_change},
        )


def get_inst_quarterly(code: str) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM inst_quarterly WHERE code=:code ORDER BY quarter DESC LIMIT 1",
            {"code": code},
        ).fetchone()
        return dict(row) if row else {}


# ── 机构前兆信号缓存（US-69）────────────────────────────────────────

def save_precursor_cache(code: str, survey: dict, short_selling: dict,
                         participation: dict, score: float, is_active: bool):
    """写入前兆缓存。survey 为空时保留缓存里 30 天内的旧事件。"""
    fetched_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")

    survey_to_save = survey
    new_events = (survey or {}).get("events") or []
    if not new_events:
        old = get_precursor_cache(code)
        old_events = (old.get("survey") or {}).get("events") or []
        if old_events:
            try:
                cutoff = datetime.now(CN_TZ) - timedelta(days=30)
                fresh = [
                    e for e in old_events
                    if datetime.strptime(e["date"][:10], "%Y-%m-%d") >= cutoff.replace(tzinfo=None)
                ]
                if fresh:
                    survey_to_save = {**(survey or {}), "events": fresh}
            except Exception:
                pass

    with get_conn() as c:
        c.execute(
            """
            INSERT INTO stock_precursor_cache
               (code, fetched_at, survey_json, short_json, partic_json, score, is_active)
               VALUES(:code,:fetched_at,:survey,:short,:partic,:score,:is_active)
            ON CONFLICT(code, fetched_at) DO UPDATE SET
               survey_json=excluded.survey_json, short_json=excluded.short_json,
               partic_json=excluded.partic_json, score=excluded.score, is_active=excluded.is_active
            """,
            {
                "code": code, "fetched_at": fetched_at,
                "survey": json.dumps(survey_to_save, ensure_ascii=False) if survey_to_save else None,
                "short": json.dumps(short_selling, ensure_ascii=False) if short_selling else None,
                "partic": json.dumps(participation, ensure_ascii=False) if participation else None,
                "score": score, "is_active": int(is_active),
            },
        )
        # 同时写入 precursor_history（每日快照，INSERT OR IGNORE 不覆盖历史）
        today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
        try:
            c.execute(
                """
                INSERT OR IGNORE INTO precursor_history
                    (code, snapshot_date, survey_json, short_json, participation_json)
                VALUES (:code, :date, :survey, :short, :partic)
                """,
                {
                    "code": code, "date": today,
                    "survey": json.dumps(survey_to_save, ensure_ascii=False) if survey_to_save else None,
                    "short":  json.dumps(short_selling,  ensure_ascii=False) if short_selling  else None,
                    "partic": json.dumps(participation,  ensure_ascii=False) if participation  else None,
                },
            )
            # 清理 90 天以外的旧快照
            c.execute(
                "DELETE FROM precursor_history WHERE code=:code AND snapshot_date < date('now','-90 days')",
                {"code": code},
            )
        except Exception:
            pass

        all_events = list(new_events) or []
        if not all_events and survey_to_save:
            all_events = survey_to_save.get("events") or []
        for ev in all_events:
            try:
                c.execute(
                    """
                    INSERT INTO survey_events(code, event_date, n_inst, is_specific, source)
                    VALUES(:code,:event_date,:n_inst,:is_specific,:source)
                    ON CONFLICT DO NOTHING
                    """,
                    {
                        "code": code, "event_date": str(ev.get("date", ""))[:10],
                        "n_inst": int(ev.get("n_inst") or 0),
                        "is_specific": int(bool(ev.get("is_specific"))),
                        "source": ev.get("source", ""),
                    },
                )
            except Exception:
                pass


def get_precursor_cache(code: str) -> dict:
    """返回最新缓存记录；survey.events 为空时从 survey_events 永久表补回近60天数据。"""
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM stock_precursor_cache WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
            {"code": code},
        ).fetchone()
    if not row:
        return {}
    rec = dict(row)
    try:
        if rec.get("survey_json"):
            rec["survey"] = json.loads(rec["survey_json"])
        if rec.get("short_json"):
            rec["short_selling"] = json.loads(rec["short_json"])
        if rec.get("partic_json"):
            rec["participation"] = json.loads(rec["partic_json"])
        fetched = datetime.fromisoformat(rec["fetched_at"].replace(" ", "T"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=CN_TZ)
        rec["age_hours"] = (datetime.now(CN_TZ) - fetched).total_seconds() / 3600
    except Exception:
        rec["age_hours"] = 999

    cached_events = (rec.get("survey") or {}).get("events") or []
    if not cached_events:
        try:
            cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            with get_conn() as c:
                perm_rows = c.execute(
                    "SELECT event_date, n_inst, is_specific FROM survey_events "
                    "WHERE code=:code AND event_date>=:cutoff ORDER BY event_date DESC",
                    {"code": code, "cutoff": cutoff},
                ).fetchall()
            if perm_rows:
                events = [
                    {"date": r["event_date"], "n_inst": r["n_inst"],
                     "is_specific": bool(r["is_specific"]), "source": "survey_events"}
                    for r in perm_rows
                ]
                rec["survey"] = {**(rec.get("survey") or {}), "events": events}
        except Exception:
            pass

    return rec


def get_precursor_summary(user_id: int, limit: int = 3) -> list:
    """返回该用户持有/观察 A 股中 is_active=1 的 Top N，按 score 降序。"""
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT p.code, s.name, p.score, p.survey_json, p.short_json, p.partic_json, p.fetched_at
            FROM stock_precursor_cache p
            JOIN stocks s ON s.code = p.code
            JOIN user_watchlist w ON w.stock_code = p.code AND w.user_id = :uid
            WHERE p.is_active = 1
              AND w.status IN ('holding','watching')
              AND p.fetched_at = (
                  SELECT MAX(fetched_at) FROM stock_precursor_cache WHERE code = p.code
              )
            ORDER BY p.score DESC
            LIMIT :limit
            """,
            {"uid": user_id, "limit": limit},
        ).fetchall()
    result = []
    for row in rows:
        rec = dict(row)
        tags = []
        try:
            sv = json.loads(rec.get("survey_json") or "{}")
            if sv.get("events"):
                specific = [e for e in sv["events"] if e.get("is_specific")]
                tags.append(f"近期{'专程拜访' if specific else '有机构调研'}")
        except Exception:
            pass
        try:
            sh = json.loads(rec.get("short_json") or "{}")
            if sh.get("trend") == "做空增加":
                pct = sh.get("change_pct", 0)
                tags.append(f"融券做空 +{pct:.0f}%")
            elif sh.get("trend") == "做空减少":
                tags.append("融券做空在减少")
        except Exception:
            pass
        try:
            pa = json.loads(rec.get("partic_json") or "{}")
            if pa.get("spike"):
                latest = pa.get("latest", 0)
                avg = pa.get("avg_30d", 0)
                diff = latest - avg
                tags.append(f"机构参与度异常（+{diff:.0f}%）")
        except Exception:
            pass
        result.append({
            "code": rec["code"],
            "name": rec["name"],
            "score": rec["score"],
            "tags": tags,
            "fetched_at": rec["fetched_at"],
        })
    return result
