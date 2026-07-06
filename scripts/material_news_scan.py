"""
US-118 编排层：检测(量化) → 解读(LLM) → 存 stock_events(source='news_material')。
只存通过漏斗且未弃答/未冲突的事件；按 code+日期+摘要去重。
"""
import json
import time

from radar_app.data.core import get_conn
from scripts.news_materiality import scan_material_news
from scripts.news_interpret import interpret_event


def _stock_name(code: str) -> str:
    with get_conn() as c:
        r = c.execute("SELECT COALESCE(name_cn, name) n FROM stocks WHERE code=:c", {"c": code}).fetchone()
    return (r["n"] if r else "") or ""


def _stock_market(code: str) -> str:
    with get_conn() as c:
        r = c.execute("SELECT market FROM stocks WHERE code=:c", {"c": code}).fetchone()
    return (r["market"] if r else "cn") or "cn"


def run_material_scan(code: str, name: str = "", market: str = "", days: int = 7) -> dict:
    name = name or _stock_name(code)
    market = market or _stock_market(code)
    items = scan_material_news(code, name, market, days=days)

    saved = alerted = 0
    for item in items:
        interp = interpret_event(item, code, name, market)
        time.sleep(1)  # Groq 30 RPM 限速
        if interp["abstained"] or interp["conflict"]:
            continue  # 弃答/方向矛盾不存
        summary = (interp["explain"] or item["title"])[:120]
        detail = {
            "title": item["title"], "source": item["source"],
            "score": item["score"], "tier": item["tier"],
            "ar": item["ar"], "ar_z": item["ar_z"], "vol_z": item["vol_z"],
            "market_status": item.get("market_status"), "is_early": item.get("is_early", 0),
            "aggregate_volume": item["aggregate_volume"], "event_types": item["event_types"],
            "direction": interp["direction"], "explain": interp["explain"],
            "evidence_quote": interp["evidence_quote"], "watch": interp["watch"],
            "confidence": interp["confidence"],
        }
        with get_conn() as c:
            exists = c.execute(
                "SELECT id FROM stock_events WHERE code=:c AND event_date=:d AND summary=:s AND source='news_material'",
                {"c": code, "d": item["date"], "s": summary},
            ).fetchone()
            if exists:
                continue
            c.execute(
                "INSERT INTO stock_events(code,event_type,event_date,summary,detail_json,source) "
                "VALUES(:c,'news_material',:d,:s,:j,'news_material')",
                {"c": code, "d": item["date"], "s": summary, "j": json.dumps(detail, ensure_ascii=False)},
            )
        saved += 1
        if item["tier"] == "material":
            alerted += 1
    return {"scanned": len(items), "saved": saved, "material": alerted}


def run_material_scan_all(codes: list[str], days: int = 7) -> dict:
    total = {"saved": 0, "material": 0}
    for code in codes:
        try:
            r = run_material_scan(code, days=days)
            total["saved"] += r["saved"]
            total["material"] += r["material"]
        except Exception as e:
            print(f"  material_scan {code} failed: {e}")
    return total


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "300274"
    print(run_material_scan(code, days=30))
