"""
每日摘要模块：precursor scan 结束后调用。
1. 从 DB 拿妈妈（user_id=2）的自选股完整快照
2. 用 Groq 选出 3-5 只信号最强的，生成简报
3. 推送 Server酱（微信）
4. 把完整快照 JSON commit 到 GitHub repo，供 Claude Routine 读取
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
# WeChat 推送（Groq 生成简报）
# ─────────────────────────────────────────────────────────────────

def _pick_top_stocks(stocks: list, n: int = 5) -> list:
    """按信号强度选出最值得推送的 n 只股票。"""
    scored = []
    for s in stocks:
        if s.get("market") != "cn":
            continue
        prec = s.get("precursor") or {}
        ana = s.get("analysis") or {}
        grade = (ana.get("grade") or "")[:1]
        if grade in ("D", "E", "F") and not prec.get("is_active"):
            continue

        score = 0
        # 信号分
        score += (prec.get("score") or 0) * 2
        # 今日异动
        chg = (s.get("price") or {}).get("change_pct") or 0
        score += abs(chg) * 0.5
        # 是新股
        if s.get("is_new"):
            score += 3
        # 评级质量
        score += {"A": 4, "B": 2, "C": 0}.get(grade, 0)

        scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:n]]


def _groq_digest(top_stocks: list, today_str: str) -> str:
    """用 Groq 生成今日简报文本。"""
    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

        lines = []
        for s in top_stocks:
            ana = s.get("analysis") or {}
            prec = s.get("precursor") or {}
            price_info = s.get("price") or {}
            chg = price_info.get("change_pct")
            chg_str = f" {chg:+.1f}%" if chg is not None else ""
            survey = prec.get("survey") or {}
            lines.append(
                f"- {s['name']}({s['code']}) 评级:{ana.get('grade','?')} "
                f"量化:{ana.get('quant_score','?')}/100 "
                f"今日:{chg_str} "
                f"30天调研:{survey.get('count_30d',0)}次 "
                f"前兆信号:{prec.get('score',0):.1f} "
                f"结论:{(ana.get('reasoning') or '')[:80]}"
            )

        prompt = f"""今天是{today_str}，以下是自选股中信号最强的几只股票数据：

{chr(10).join(lines)}

请用妈妈能看懂的语言，写一段每日推送。要求：
1. 纯文本，不用markdown符号
2. 每只股票2-3句：公司做什么 + 今天信号说明什么 + 操作建议
3. 结尾一句总结今日市场氛围
4. 全文不超过600字"""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            timeout=60,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("[daily_digest] Groq 生成失败: %s", e)
        # 降级：纯规则文本
        lines = []
        for s in top_stocks:
            ana = s.get("analysis") or {}
            chg = (s.get("price") or {}).get("change_pct")
            chg_str = f" {chg:+.1f}%" if chg is not None else ""
            lines.append(f"◆ {s['name']} ({s['code']}){chg_str} — 评级{ana.get('grade','?')}: {(ana.get('reasoning') or '')[:80]}")
        return "\n\n".join(lines)


def _send_wechat(title: str, content: str):
    key = os.environ.get("SERVERCHAN_KEY", "")
    if not key:
        logger.warning("[daily_digest] SERVERCHAN_KEY 未配置，跳过微信推送")
        return
    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            json={"title": title, "desp": content},
            timeout=15,
        )
        logger.info("[daily_digest] 微信推送: %s", r.json())
    except Exception as e:
        logger.warning("[daily_digest] 微信推送失败: %s", e)


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
    """precursor_scheduler 扫描完成后调用。"""
    today_str = date.today().strftime("%Y年%m月%d日")
    logger.info("[daily_digest] 开始每日摘要…")

    try:
        snapshot = _build_snapshot(MOM_USER_ID)
        if not snapshot:
            logger.warning("[daily_digest] user_id=%d 无自选股，跳过", MOM_USER_ID)
            return

        # 1. 提交快照到 GitHub（供 Claude Routine 读取）
        _commit_snapshot_to_github(snapshot)

        # 2. 选出今日重点股票
        top = _pick_top_stocks(snapshot.get("stocks", []))
        if not top:
            logger.info("[daily_digest] 今日无信号股票，跳过微信推送")
            return

        # 3. 生成文本 + 推送微信
        body = _groq_digest(top, today_str)
        title = f"每日五选 {today_str}"
        _send_wechat(title, body)
        logger.info("[daily_digest] 完成，推送了 %d 只股票", len(top))

    except Exception as e:
        logger.warning("[daily_digest] run_daily_digest 异常: %s", e, exc_info=True)
