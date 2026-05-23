"""
每日摘要模块：precursor scan 结束后调用。
1. 从 DB 拿妈妈（user_id=2）的自选股完整快照（含价格/评级/前兆信号/新闻）
2. 把完整快照 JSON commit 到 GitHub repo，供 Claude Routine 读取
推送由 Claude Routine 生成内容 → GitHub Actions 发 Server酱。
"""

import base64
import json
import logging
import os
from datetime import date, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

GITHUB_REPO = "Sodawaitress/personal-buffett"
SNAPSHOT_PATH = "snapshots/daily_snapshot.json"
MOM_USER_ID = 2


# ─────────────────────────────────────────────────────────────────
# 快照构建（复用 /api/claude-summary 的逻辑，直接从 DB 读）
# ─────────────────────────────────────────────────────────────────

def _build_snapshot(user_id: int) -> dict:
    """构建用户自选股完整快照。"""
    from radar_app.data.analysis import get_latest_analysis
    from radar_app.data.core import get_conn
    from radar_app.data.market import get_precursor_cache
    from radar_app.data.stocks import get_user_watchlist
    from radar_app.shared.market import detect_market

    added_cutoff = date.today() - timedelta(days=7)
    wl = get_user_watchlist(user_id)
    if not wl:
        return {}

    stocks = []
    for row in wl:
        code = row.get("stock_code") or row.get("code", "")
        market = row.get("market") or detect_market(code)
        name = row.get("name_cn") or row.get("name") or code
        added_at = str(row.get("added_at") or "")[:10]
        is_new = bool(added_at and date.fromisoformat(added_at) >= added_cutoff)

        snap = {
            "code": code, "name": name, "market": market,
            "status": row.get("status", "watching"),
            "entry_price": row.get("buy_price"),
            "added_at": added_at, "is_new": is_new,
        }

        ana = get_latest_analysis(code)
        if ana:
            snap["analysis"] = {
                "date": ana.get("analysis_date", ""),
                "grade": ana.get("grade", ""),
                "conclusion": ana.get("conclusion", ""),
                "moat": ana.get("moat", ""),
                "reasoning": (ana.get("reasoning") or "")[:300],
                "quant_score": ana.get("quant_score"),
                "data_incomplete": ana.get("data_incomplete", 0),
            }
        else:
            snap["analysis"] = None

        if market == "cn":
            pc = get_precursor_cache(code)
            if pc:
                sv = pc.get("survey") or {}
                sh = pc.get("short_selling") or {}
                events = sv.get("events") or []
                latest_date = max((e.get("date", "") for e in events if e.get("date")), default=None)
                days_since = None
                if latest_date:
                    try:
                        days_since = (date.today() - date.fromisoformat(latest_date)).days
                    except Exception:
                        pass
                snap["precursor"] = {
                    "cache_age_hours": round(pc.get("age_hours", 999), 1),
                    "score": pc.get("score", 0),
                    "is_active": bool(pc.get("is_active")),
                    "survey": {
                        "count_30d": len(events),
                        "days_since_latest": days_since,
                        "events": [
                            {"date": e.get("date", "")[:10], "n_inst": e.get("n_inst", 0),
                             "method": e.get("method", ""), "is_specific": e.get("is_specific", False)}
                            for e in events[:5]
                        ],
                    },
                    "short_selling": {
                        "change_pct": sh.get("change_pct"),
                        "direction": sh.get("direction", ""),
                    },
                }
            else:
                snap["precursor"] = None
        else:
            snap["precursor"] = None

        try:
            with get_conn() as c:
                pr = c.execute(
                    "SELECT price, change_pct FROM stock_prices WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
                    {"code": code}
                ).fetchone()
                if pr:
                    snap["price"] = {"current": pr["price"], "change_pct": pr["change_pct"]}
        except Exception:
            pass

        try:
            with get_conn() as c:
                rows = c.execute(
                    "SELECT title, sentiment, published_at FROM stock_news WHERE code=:code ORDER BY published_at DESC LIMIT 5",
                    {"code": code}
                ).fetchall()
                if rows:
                    snap["news"] = [
                        {"title": r["title"], "sentiment": r["sentiment"], "date": str(r["published_at"] or "")[:10]}
                        for r in rows
                    ]
        except Exception:
            pass

        stocks.append(snap)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "stocks": stocks,
    }



# ─────────────────────────────────────────────────────────────────
# GitHub commit
# ─────────────────────────────────────────────────────────────────

def _commit_snapshot_to_github(snapshot: dict):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.warning("[daily_digest] GITHUB_TOKEN 未配置，跳过 GitHub 快照提交")
        return

    content_bytes = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    encoded = base64.b64encode(content_bytes).decode()
    today = date.today().isoformat()

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SNAPSHOT_PATH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 获取当前文件 SHA（更新时需要）
    sha = None
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    payload = {
        "message": f"chore: daily snapshot {today}",
        "content": encoded,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            logger.info("[daily_digest] GitHub 快照已提交: %s", today)
        else:
            logger.warning("[daily_digest] GitHub commit 失败: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("[daily_digest] GitHub commit 异常: %s", e)


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────

def run_daily_digest():
    """precursor_scheduler 扫描完成后调用。只生成快照并提交到 GitHub，推送由 Claude Routine + GitHub Actions 负责。"""
    logger.info("[daily_digest] 开始每日快照生成…")

    try:
        snapshot = _build_snapshot(MOM_USER_ID)
        if not snapshot:
            logger.warning("[daily_digest] user_id=%d 无自选股，跳过", MOM_USER_ID)
            return

        _commit_snapshot_to_github(snapshot)
        logger.info("[daily_digest] 快照已提交 GitHub，共 %d 只股票", len(snapshot.get("stocks", [])))

    except Exception as e:
        logger.warning("[daily_digest] run_daily_digest 异常: %s", e, exc_info=True)
