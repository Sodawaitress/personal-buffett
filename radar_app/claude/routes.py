"""
/api/claude-summary  —  Claude Routine 数据端点
返回用户自选股的完整信号快照，供 Claude 做每日分析和质量评估。
用 CLAUDE_ROUTINE_TOKEN 做简单鉴权，Claude routine 在 URL 里带 token 参数。
"""

import json
import os
from datetime import date, datetime, timedelta

from flask import jsonify, request

from sqlalchemy import text

from radar_app.data.analysis import get_latest_analysis
from radar_app.data.core import get_conn
from radar_app.data.market import get_precursor_cache
from radar_app.data.stocks import get_user_watchlist
from radar_app.shared.market import detect_market
from scripts.buffett_utils import summarize_to_sentence


def _token_ok() -> bool:
    expected = os.environ.get("CLAUDE_ROUTINE_TOKEN", "")
    if not expected:
        return False
    return request.args.get("token", "") == expected


def _strip_html(s: str) -> str:
    """粗糙去 HTML tag，用于把 letter_html 变成纯文本摘要。"""
    if not s:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", s)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]


def _survey_quality(method: str) -> str:
    """返回调研方式的质量标签。"""
    m = method.lower()
    if any(k in m for k in ("现场参观", "实地调研", "工厂")):
        return "现场参观★★★★★"
    if "特定对象" in m:
        return "特定调研★★★★"
    if "策略会" in m and "实地" in m:
        return "策略会+实地★★★★"
    if "电话" in m or "网络" in m:
        return "电话会★★★"
    if "业绩说明" in m:
        return "业绩说明会★★"
    return "其他★★"


def _build_stock_snapshot(wl_row: dict, added_cutoff: date) -> dict:
    code = wl_row["stock_code"] or wl_row.get("code", "")
    market = wl_row.get("market") or detect_market(code)
    name = wl_row.get("name_cn") or wl_row.get("name") or code
    status = wl_row.get("status", "watching")
    entry_price = wl_row.get("buy_price") or wl_row.get("entry_price")
    added_at = str(wl_row.get("added_at") or "")[:10]
    is_new = bool(added_at and date.fromisoformat(added_at) >= added_cutoff)

    snap: dict = {
        "code": code,
        "name": name,
        "market": market,
        "status": status,
        "entry_price": entry_price,
        "added_at": added_at,
        "is_new": is_new,
    }

    # ── 最新 LLM 分析 ──
    analysis = get_latest_analysis(code)
    if analysis:
        snap["analysis"] = {
            "date": analysis.get("analysis_date", ""),
            "grade": analysis.get("grade", ""),
            "conclusion": analysis.get("conclusion", ""),
            "moat": analysis.get("moat", ""),
            "reasoning": summarize_to_sentence(analysis.get("reasoning") or "", 300),
            "trade_block": analysis.get("trade_block", ""),
            "framework": analysis.get("framework_used", ""),
            "quant_score": analysis.get("quant_score"),
            "letter_text": _strip_html(analysis.get("letter_html", "")),
        }
    else:
        snap["analysis"] = None

    # ── 前兆信号缓存（仅 A 股）──
    if market == "cn":
        pc = get_precursor_cache(code)
        if pc:
            sv = pc.get("survey") or {}
            sh = pc.get("short_selling") or {}
            pt = pc.get("participation") or {}

            # 调研事件列表
            events = sv.get("events") or []
            survey_items = []
            for ev in events[:5]:
                d = str(ev.get("date", ""))[:10]
                n = ev.get("n_inst", 0)
                method = ev.get("method", "")
                survey_items.append({
                    "date": d,
                    "n_inst": n,
                    "method": method,
                    "quality": _survey_quality(method),
                    "is_specific": ev.get("is_specific", False),
                })
            # 最新一次调研距今天数
            latest_survey_date = max((e["date"] for e in survey_items if e["date"]), default=None)
            days_since_survey = None
            if latest_survey_date:
                try:
                    days_since_survey = (date.today() - date.fromisoformat(latest_survey_date)).days
                except Exception:
                    pass

            snap["precursor"] = {
                "cache_age_hours": round(pc.get("age_hours", 999), 1),
                "score": pc.get("score", 0),
                "is_active": bool(pc.get("is_active")),
                "survey": {
                    "score": sv.get("score", 0),
                    "count_30d": len(events),
                    "days_since_latest": days_since_survey,
                    "events": survey_items,
                },
                "short_selling": {
                    "valid": sh.get("valid", False),
                    "change_pct": sh.get("change_pct"),
                    "direction": sh.get("direction", ""),
                    "desc": sh.get("desc", ""),
                },
                "participation": {
                    "valid": pt.get("valid", False),
                    "latest": pt.get("latest"),
                    "avg_30d": pt.get("avg_30d"),
                    "spike": pt.get("spike", False),
                    "desc": pt.get("desc", ""),
                },
            }
        else:
            snap["precursor"] = None
    else:
        snap["precursor"] = None

    # ── 最新价格 ──
    with get_conn() as c:
        price_row = c.execute(
            "SELECT price, change_pct FROM stock_prices WHERE code=:code ORDER BY fetched_at DESC LIMIT 1",
            {"code": code},
        ).fetchone()
        if price_row:
            snap["price"] = {"current": price_row["price"], "change_pct": price_row["change_pct"]}

    # ── 最近新闻情绪 ──
    with get_conn() as c:
        news_rows = c.execute(
            """SELECT title, sentiment, source, publish_time
               FROM stock_news WHERE code=:code
               ORDER BY publish_time DESC LIMIT 5""",
            {"code": code},
        ).fetchall()
        if news_rows:
            snap["recent_news"] = [
                {
                    "title": r["title"][:80],
                    "sentiment": r["sentiment"],
                    "source": r["source"],
                    "date": str(r["publish_time"] or "")[:10],
                }
                for r in news_rows
            ]

    return snap


def _ensure_log_table():
    with get_conn() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS claude_improvement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                stock_name TEXT,
                stock_code TEXT,
                entry_type TEXT,
                content TEXT NOT NULL
            )
        """))


def register_claude_routes(app):

    @app.route("/api/improvement-log", methods=["POST"])
    def improvement_log_write():
        """
        POST /api/improvement-log
        Body: {entry_date, stock_name, stock_code, entry_type, content}
        Claude Routine 用来存储每日改进日志（云端无法写本地文件）。
        """
        if not _token_ok():
            return jsonify({"error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "content required"}), 400

        _ensure_log_table()
        with get_conn() as c:
            c.execute(
                text("""INSERT INTO claude_improvement_log
                   (logged_at, entry_date, stock_name, stock_code, entry_type, content)
                   VALUES (:logged_at, :entry_date, :stock_name, :stock_code, :entry_type, :content)"""),
                {
                    "logged_at": datetime.utcnow().isoformat() + "Z",
                    "entry_date": data.get("entry_date", date.today().isoformat()),
                    "stock_name": data.get("stock_name", ""),
                    "stock_code": data.get("stock_code", ""),
                    "entry_type": data.get("entry_type", "comparison"),
                    "content": content,
                },
            )
        return jsonify({"ok": True})

    @app.route("/api/improvement-log", methods=["GET"])
    def improvement_log_read():
        """GET /api/improvement-log?token=XXX&limit=20 — 查看最近的改进日志"""
        if not _token_ok():
            return jsonify({"error": "unauthorized"}), 401

        limit = min(int(request.args.get("limit", 20)), 100)
        _ensure_log_table()
        with get_conn() as c:
            rows = c.execute(
                text("SELECT * FROM claude_improvement_log ORDER BY id DESC LIMIT :limit"),
                {"limit": limit},
            ).fetchall()
        return jsonify({"entries": [dict(r) for r in rows]})

    @app.route("/api/claude-summary")
    def claude_summary():
        """
        GET /api/claude-summary?token=XXX&user_id=2
        返回指定用户自选股的完整信号快照，供 Claude routine 分析。
        """
        if not _token_ok():
            return jsonify({"error": "unauthorized"}), 401

        try:
            user_id = int(request.args.get("user_id", 0))
        except ValueError:
            return jsonify({"error": "invalid user_id"}), 400
        if not user_id:
            return jsonify({"error": "user_id required"}), 400

        # 7天内新加的股票标记为 is_new
        added_cutoff = date.today() - timedelta(days=7)

        wl = get_user_watchlist(user_id)
        if not wl:
            return jsonify({"error": "no watchlist", "user_id": user_id}), 404

        stocks = []
        for row in wl:
            try:
                snap = _build_stock_snapshot(row, added_cutoff)
                stocks.append(snap)
            except Exception as e:
                stocks.append({
                    "code": row.get("stock_code", "?"),
                    "error": str(e),
                })

        # 汇总统计
        cn_stocks = [s for s in stocks if s.get("market") == "cn" and "error" not in s]
        active_signals = [s for s in cn_stocks if (s.get("precursor") or {}).get("is_active")]
        new_stocks = [s for s in stocks if s.get("is_new") and "error" not in s]
        no_analysis = [s for s in stocks if not s.get("analysis") and "error" not in s]

        return jsonify({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "summary": {
                "total": len(stocks),
                "cn_stocks": len(cn_stocks),
                "active_signals": len(active_signals),
                "new_stocks_this_week": len(new_stocks),
                "pending_analysis": len(no_analysis),
            },
            "stocks": stocks,
        })
