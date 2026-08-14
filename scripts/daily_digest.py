"""
每日摘要模块：precursor scan 结束后调用。
1. 从 DB 汇总所有用户自选股（去重），构建完整快照（含价格/评级/前兆信号/新闻）
2. 把完整快照 JSON commit 到 GitHub repo，供 Claude Routine 读取
推送由 Claude Routine 生成内容 → GitHub Actions 发 Server酱。
"""

import base64
import json
import logging
import os
from datetime import date, datetime, timedelta

import requests
from scripts.buffett_utils import summarize_to_sentence

logger = logging.getLogger(__name__)

GITHUB_REPO = "Sodawaitress/personal-buffett"
SNAPSHOT_PATH = "snapshots/daily_snapshot.json"


# ─────────────────────────────────────────────────────────────────
# 快照构建：汇总所有用户的不重复股票
# ─────────────────────────────────────────────────────────────────

def _get_all_watchlist_rows() -> list:
    """从 DB 拿所有用户自选股，按 stock_code 去重（保留最早添加的那条）。"""
    from radar_app.data.core import get_conn
    with get_conn() as c:
        rows = c.execute("""
            -- s.name 必须一起取：全库 name_cn 都是 NULL，公司名实际存在 name 列。
            -- 少取这一列 → 快照里 208 只股票的 name 全部回落成代码 → Routine 没有
            -- 名字来源，只能自己「填」公司名，填错了也没人知道（002414 高德红外
            -- 被写成海康威视，进了妈妈读的日报）。US-140。
            SELECT w.stock_code, s.market, s.name, s.name_cn,
                   w.status, w.buy_price, w.added_at, w.user_id
            FROM user_watchlist w
            LEFT JOIN stocks s ON s.code = w.stock_code
            WHERE w.removed_at IS NULL
            ORDER BY w.added_at ASC
        """).fetchall()
    # 按 stock_code 去重(保留最早添加的那条)+ 聚合 watched_by —— Python 做，避开 SQLite/Postgres 方言差异
    by_code: dict = {}
    for r in rows or []:
        d = dict(r)
        code = d["stock_code"]
        uid = str(d.pop("user_id", ""))
        if code not in by_code:
            by_code[code] = {**d, "watched_by": [uid]}
        else:
            by_code[code]["watched_by"].append(uid)
    out = []
    for d in by_code.values():
        d["watched_by"] = ",".join(x for x in d["watched_by"] if x)
        out.append(d)
    return out


def _build_snapshot() -> dict:
    """构建全平台自选股完整快照（所有用户去重合并）。"""
    from radar_app.data.analysis import get_latest_analysis
    from radar_app.data.core import get_conn
    from radar_app.data.market import get_precursor_cache
    from radar_app.shared.market import detect_market

    added_cutoff = date.today() - timedelta(days=7)
    wl = _get_all_watchlist_rows()
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
            "watched_by": str(row.get("watched_by") or ""),
        }

        ana = get_latest_analysis(code)
        if ana:
            moat = ana.get("moat", "")
            q = ana.get("quant_score")
            is_incomplete = "0/35" in moat or (q is not None and q < 15)
            snap["analysis"] = {
                "date": ana.get("analysis_date", ""),
                "grade": ana.get("grade", ""),
                "conclusion": ana.get("conclusion", ""),
                "moat": moat,
                "reasoning": summarize_to_sentence(ana.get("reasoning") or "", 300),
                "quant_score": q,
                "data_incomplete": ana.get("data_incomplete", 0),
                "data_quality": "incomplete" if is_incomplete else "ok",
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
            # 跨方言：DATE('now','-1 day') 是 SQLite 专用，在 Neon/Postgres 抛错 → 被下面
            # except 吞掉 → 每只 price=None → fresh=0 → 撞 50% 闸 → 快照冻结(07-02 真因)。
            # 改为 Python 算 cutoff 传参，ISO 文本字典序=时间序，两方言通用。
            price_cutoff = (date.today() - timedelta(days=1)).isoformat()
            with get_conn() as c:
                pr = c.execute(
                    "SELECT price, change_pct, fetched_at FROM stock_prices "
                    "WHERE code=:code AND fetched_at >= :cutoff "
                    "ORDER BY fetched_at DESC LIMIT 1",
                    {"code": code, "cutoff": price_cutoff}
                ).fetchone()
                if pr:
                    snap["price"] = {
                        "current": pr["price"],
                        "change_pct": pr["change_pct"],
                        "fetched_at": str(pr["fetched_at"] or "")[:19],
                    }
                else:
                    snap["price"] = None
        except Exception:
            snap["price"] = None

        try:
            with get_conn() as c:
                rows = c.execute(
                    "SELECT title, sentiment, publish_time FROM stock_news WHERE code=:code ORDER BY publish_time DESC LIMIT 5",
                    {"code": code}
                ).fetchall()
                if rows:
                    snap["news"] = [
                        {"title": r["title"], "sentiment": r["sentiment"], "date": str(r["publish_time"] or "")[:10]}
                        for r in rows
                    ]
        except Exception:
            pass

        stocks.append(snap)

    import hashlib
    fresh_prices = [s for s in stocks if s.get("price") is not None]
    sig_input = sorted([
        (s["code"], (s.get("price") or {}).get("current"), (s.get("price") or {}).get("change_pct"))
        for s in stocks
    ])
    price_signature = hashlib.md5(json.dumps(sig_input).encode()).hexdigest()

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scope": "all_users",
        "price_snapshot_at": datetime.utcnow().isoformat() + "Z",
        "stocks_with_fresh_price": len(fresh_prices),
        "stocks_total": len(stocks),
        "price_signature": price_signature,
        "stocks": stocks,
    }



# ─────────────────────────────────────────────────────────────────
# GitHub commit
# ─────────────────────────────────────────────────────────────────

def _commit_snapshot_to_github(snapshot: dict) -> bool:
    """返回是否真的提交成功 —— 调用方要据此决定服务成败（US-140）。
    此前无论 403/熔断/token 缺失都静默返回，外层照打 ✅，快照冻了 14 天没人知道。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.error(
            "[daily_digest] GITHUB_TOKEN 未配置 — 快照将无法提交到 GitHub，"
            "Claude Routine 会读到陈旧快照。"
            "在 Fly.io 设置: flyctl secrets set GITHUB_TOKEN=<PAT>"
        )
        return False

    fresh = snapshot.get("stocks_with_fresh_price", 0)
    total = snapshot.get("stocks_total", 0)
    if total > 0 and fresh / total < 0.5:
        logger.error(
            "[daily_digest] 中止 commit — 只有 %d/%d (%.0f%%) 只股票有当日新价格。"
            "AKShare 抓价可能挂了，不覆盖 GitHub 上的旧快照。"
            "2026-07-01 事故教训：宁可让 Routine 读到昨天的 snapshot 并识别为陈旧，"
            "也不要用只翻新元数据的伪 snapshot 骗过 Routine。",
            fresh, total, (fresh / total * 100)
        )
        return False

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
            return True
        else:
            logger.error(
                "[daily_digest] GitHub commit 失败: HTTP %s — 快照未更新。"
                "401=token过期，403=权限不足，422=SHA冲突。响应: %s",
                r.status_code, r.text[:300]
            )
    except Exception as e:
        logger.warning("[daily_digest] GitHub commit 异常: %s", e)
    return False


# ─────────────────────────────────────────────────────────────────
# 预言存库（读 GitHub → INSERT signal_predictions → 清空文件）
# ─────────────────────────────────────────────────────────────────

PREDICTIONS_PATH = "output/predictions_pending.json"

def _ingest_predictions_from_github():
    """读取 Routine 写的预言 JSON，存入 signal_predictions，然后清空文件。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PREDICTIONS_PATH}"

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return
        data = r.json()
        sha = data.get("sha")
        content = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
        if not content:
            return
    except Exception as e:
        logger.warning("[daily_digest] 读取预言文件失败: %s", e)
        return

    # 存入 DB
    try:
        from radar_app.data.core import get_conn
        with get_conn() as c:
            for p in content:
                code = p.get("code", "")
                if not code:
                    continue
                c.execute("""
                    INSERT INTO signal_predictions
                        (code, direction, note, signal_snapshot, created_at)
                    VALUES (:code, :direction, :note, :snapshot, :created_at)
                """, {
                    "code": code,
                    "direction": p.get("direction", ""),
                    "note": p.get("key_signal", ""),
                    "snapshot": json.dumps({
                        "name": p.get("name"),
                        "price_at_prediction": p.get("price_at_prediction"),
                        "horizon_days": p.get("horizon_days", 10),
                        "key_signal": p.get("key_signal"),
                    }, ensure_ascii=False),
                    "created_at": p.get("date", date.today().isoformat()),
                })
        logger.info("[daily_digest] 存入 %d 条预言", len(content))
    except Exception as e:
        logger.warning("[daily_digest] 预言存库失败: %s", e)
        return

    # 清空文件（写空数组），避免重复存入
    try:
        empty = base64.b64encode(b"[]").decode()
        requests.put(url, headers=headers, json={
            "message": f"chore: ingest predictions {date.today().isoformat()}",
            "content": empty, "sha": sha, "branch": "main",
        }, timeout=10)
    except Exception as e:
        logger.warning("[daily_digest] 清空预言文件失败: %s", e)


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────

def run_daily_digest():
    """precursor_scheduler 扫描完成后调用。只生成快照并提交到 GitHub，推送由 Claude Routine + GitHub Actions 负责。"""
    logger.info("[daily_digest] 开始每日快照生成…")

    try:
        snapshot = _build_snapshot()
        if not snapshot:
            logger.warning("[daily_digest] 无自选股数据，跳过")
            return False

        committed = _commit_snapshot_to_github(snapshot)
        if committed:
            logger.info("[daily_digest] 快照已提交 GitHub，共 %d 只股票", len(snapshot.get("stocks", [])))
        else:
            logger.error("[daily_digest] 快照未能提交 GitHub —— Routine 会继续读到陈旧快照")

        _ingest_predictions_from_github()
        return committed

    except Exception as e:
        logger.warning("[daily_digest] run_daily_digest 异常: %s", e, exc_info=True)
        return False
