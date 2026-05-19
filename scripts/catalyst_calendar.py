"""
US-38: 业绩日历与催化剂追踪
Fetches upcoming unlock events and financial notices for watchlist stocks.
Stores results in stock_events table (source='auto_unlock' / 'auto_notice').
"""

import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def _get_cn_codes() -> set:
    from radar_app.data.stocks import get_all_cn_watchlist_stocks
    return {code for code, _ in get_all_cn_watchlist_stocks()}


def fetch_unlock_events(codes: set, days_ahead: int = 90) -> list:
    """Return upcoming restricted-share unlock events for watchlist codes."""
    import akshare as ak

    today = date.today()
    end = today + timedelta(days=days_ahead)
    try:
        df = ak.stock_restricted_release_detail_em(
            start_date=today.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
    except Exception as e:
        logger.warning("fetch_unlock_events failed: %s", e)
        return []

    events = []
    for _, row in df.iterrows():
        code = str(row.get("股票代码", "")).zfill(6)
        if code not in codes:
            continue
        unlock_date = str(row.get("解禁时间", ""))[:10]
        unlock_type = row.get("限售股类型", "")
        actual_amount = row.get("实际解禁数量", 0) or 0
        market_value = row.get("实际解禁市值", 0) or 0
        pct = row.get("占解禁前流通市值比例", 0) or 0
        pct_f = float(pct) * 100 if pct < 1 else float(pct)
        risk = "高" if pct_f >= 5 else ("中" if pct_f >= 1 else "低")
        summary = f"限售解禁·{unlock_type}·{pct_f:.1f}%流通市值·风险:{risk}"
        events.append({
            "code": code,
            "event_type": "share_unlock",
            "event_date": unlock_date,
            "summary": summary,
            "detail": {
                "unlock_type": unlock_type,
                "actual_amount": float(actual_amount),
                "market_value_cny": float(market_value),
                "pct_of_float": round(pct_f, 2),
                "risk_level": risk,
            },
        })
    return events


def fetch_today_notices(codes: set) -> list:
    """Return financial report announcements published today for watchlist codes."""
    import akshare as ak

    today = date.today().strftime("%Y%m%d")
    events = []
    for symbol_type in ("财务报告", "重大事项"):
        try:
            df = ak.stock_notice_report(symbol=symbol_type, date=today)
        except Exception as e:
            logger.warning("stock_notice_report(%s) failed: %s", symbol_type, e)
            continue
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            if code not in codes:
                continue
            title = str(row.get("公告标题", ""))
            notice_date = str(row.get("公告日期", ""))[:10]
            events.append({
                "code": code,
                "event_type": "earnings_report" if symbol_type == "财务报告" else "major_announcement",
                "event_date": notice_date,
                "summary": title,
                "detail": {"url": row.get("网址", ""), "notice_type": symbol_type},
            })
    return events


def save_catalyst_events(events: list, source: str) -> int:
    """Upsert auto-fetched catalyst events (deduplicated by code+event_date+summary)."""
    from radar_app.data.stocks import get_conn

    saved = 0
    with get_conn() as c:
        for ev in events:
            existing = c.execute(
                "SELECT id FROM stock_events WHERE code=:code AND event_date=:ed AND summary=:s AND source=:src",
                {"code": ev["code"], "ed": ev["event_date"], "s": ev["summary"], "src": source},
            ).fetchone()
            if not existing:
                c.execute(
                    "INSERT INTO stock_events(code,event_type,event_date,summary,detail_json,source) "
                    "VALUES(:code,:et,:ed,:s,:d,:src)",
                    {
                        "code": ev["code"],
                        "et": ev["event_type"],
                        "ed": ev["event_date"],
                        "s": ev["summary"],
                        "d": json.dumps(ev["detail"], ensure_ascii=False) if ev.get("detail") else None,
                        "src": source,
                    },
                )
                saved += 1
    return saved


def prune_stale_auto_events(days_back: int = 7):
    """Remove auto-sourced events that are more than days_back days in the past."""
    from radar_app.data.stocks import get_conn

    cutoff = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    with get_conn() as c:
        c.execute(
            "DELETE FROM stock_events WHERE source IN ('auto_unlock','auto_notice') AND event_date < :cutoff",
            {"cutoff": cutoff},
        )


def run_catalyst_refresh():
    """Daily job: refresh unlock + notice events for all watchlist A-stocks."""
    codes = _get_cn_codes()
    if not codes:
        logger.info("catalyst_calendar: no CN watchlist codes, skipping")
        return

    prune_stale_auto_events()

    unlock_events = fetch_unlock_events(codes)
    n_unlock = save_catalyst_events(unlock_events, source="auto_unlock")
    logger.info("catalyst_calendar: saved %d unlock events", n_unlock)

    notice_events = fetch_today_notices(codes)
    n_notice = save_catalyst_events(notice_events, source="auto_notice")
    logger.info("catalyst_calendar: saved %d notice events", n_notice)

    return {"unlock": n_unlock, "notice": n_notice}


def get_upcoming_events_for_user(user_id: int, days_ahead: int = 7) -> list:
    """Return events in the next days_ahead days for a user's watchlist."""
    from radar_app.data.stocks import get_conn

    today = date.today().strftime("%Y-%m-%d")
    horizon = (date.today() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT e.code, s.name_cn, s.name, e.event_type, e.event_date, e.summary, e.detail_json
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
    for r in rows:
        d = dict(r)
        d["display_name"] = d.get("name_cn") or d.get("name") or d["code"]
        d["days_until"] = (date.fromisoformat(d["event_date"]) - date.today()).days
        result.append(d)
    return result


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_catalyst_refresh()
    print("Done:", result)
