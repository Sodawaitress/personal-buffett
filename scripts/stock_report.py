"""Report and push-content builders extracted from stock_pipeline."""

import db as _db

_GRADE_ORDER = ["A+", "A", "B+", "B", "B-", "C+", "C", "D", "D-"]

def _grade_rank(g):
    try:
        return _GRADE_ORDER.index(g)
    except ValueError:
        return 99

def _stock_name(code):
    s = _db.get_stock(code) or {}
    return s.get("name_cn") or s.get("name") or code

def _early_warnings_for(codes):
    """每股取一条 is_early 的重大动向。"""
    import json
    out = []
    for code in codes:
        for e in (_db.get_stock_events(code) or []):
            if e.get("source") != "news_material":
                continue
            try:
                d = json.loads(e.get("detail_json") or "{}")
            except Exception:
                continue
            if d.get("is_early"):
                out.append((code, d))
                break
    return out

def _grade_changes_for(codes):
    out = []
    for code in codes:
        hist = _db.get_analysis_history(code, period="daily", limit=2) or []
        if len(hist) >= 2:
            new_g, old_g = hist[0].get("grade"), hist[1].get("grade")
            if new_g and old_g and new_g != old_g:
                out.append((code, old_g, new_g))
    return out

def admin_user_id():
    """主 admin（role='admin'，最小 id）——全局 Server酱 有用日报用它的自选股（US-123）。"""
    try:
        from radar_app.data.core import get_conn
        with get_conn() as c:
            rows = c.execute("SELECT id FROM users WHERE role='admin' ORDER BY id ASC").fetchall()
        return rows[0]["id"] if rows else None
    except Exception:
        return None


def _signal_leads_for(codes):
    """机构领先信号（US-123）：每股一句结论，只留 lead 或 high confidence 的。"""
    try:
        from radar_app.data.signal_events import get_signal_conclusion
    except Exception:
        return []
    out = []
    for code in codes:
        try:
            sc = get_signal_conclusion(code)
        except Exception:
            sc = None
        if sc and (sc.get("lead") or sc.get("confidence") == "high") and sc.get("conclusion"):
            out.append((code, sc["conclusion"], bool(sc.get("lead"))))
    return out


def _prophet_dirs_for(codes):
    """预言线方向（US-123 复用 US-75）：机构脚印轨迹在升/降，跳过 flat。"""
    try:
        from radar_app.stocks.presenter import _build_prophet_series
    except Exception:
        return []
    out = []
    for code in codes:
        try:
            ps = _build_prophet_series(code)
        except Exception:
            ps = None
        if ps and ps.get("latest_dir") in ("rising", "falling"):
            out.append((code, ps["latest_dir"]))
    return out


_CATALYST_LABEL = {
    "share_unlock": "解禁", "auto_unlock": "解禁",
    "earnings_report": "业绩", "earnings_forecast": "业绩预告",
    "major_announcement": "重大公告", "auto_notice": "公告",
}


def _catalysts_for(user_id, days_ahead=7):
    """催化剂预警（US-123）：未来 N 天解禁/业绩/重大公告。"""
    try:
        from radar_app.data.stocks import get_upcoming_events_for_user
        return get_upcoming_events_for_user(user_id, days_ahead=days_ahead) or []
    except Exception:
        return []


def build_user_push_content(user_id: int, data: dict, ai_analysis: dict,
                             date_str: str) -> str:
    """
    今天该注意的（US-123）：早期预警 + 机构领先信号 + 预言线方向 + 评级变化 + 催化剂。
    读新鲜 DB、人话、排好序，五块全空则不推（不打扰）。任何用户通用，无硬编码。
    """
    holdings = _db.get_user_holdings(user_id) or []
    watching = _db.get_user_watching(user_id) or []
    codes = list(dict.fromkeys(list(holdings) + list(watching)))
    if not codes:
        return ""

    early     = _early_warnings_for(codes)
    leads     = _signal_leads_for(codes)
    prophets  = _prophet_dirs_for(codes)
    changes   = _grade_changes_for(codes)
    catalysts = _catalysts_for(user_id)
    if not (early or leads or prophets or changes or catalysts):
        return ""  # 无重大变化，不打扰

    lines = [f"📌 今天该注意的 · {date_str}", ""]
    if early:
        lines.append(f"🔔 早期预警（{len(early)}）")
        for code, d in early[:6]:
            tail = "（市场还没反应，你早）" if d.get("market_status") == "not_priced" else ""
            lines.append(f"· {_stock_name(code)}：{d.get('explain') or d.get('title', '')}{tail}")
        lines.append("")
    if leads:
        lines.append(f"🛰️ 机构领先信号（{len(leads)}）")
        for code, conclusion, is_lead in leads[:6]:
            badge = "⚡ " if is_lead else ""
            lines.append(f"· {badge}{_stock_name(code)}：{conclusion}")
        lines.append("")
    if prophets:
        lines.append(f"🧭 机构脚印（{len(prophets)}）")
        for code, direction in prophets[:6]:
            word = "在悄悄建仓" if direction == "rising" else "在陆续离场"
            lines.append(f"· {_stock_name(code)}：机构{word}")
        lines.append("")
    if changes:
        lines.append(f"📊 评级变化（{len(changes)}）")
        for code, old_g, new_g in changes[:8]:
            arrow = "↑" if _grade_rank(new_g) < _grade_rank(old_g) else "↓"
            lines.append(f"· {_stock_name(code)}：{old_g} → {new_g} {arrow}")
        lines.append("")
    if catalysts:
        lines.append(f"📅 催化剂预警（{len(catalysts)}）")
        for e in catalysts[:6]:
            label = _CATALYST_LABEL.get(e.get("event_type"), "事件")
            du = e.get("days_until")
            when = "今天" if du == 0 else f"{du}天后"
            name = e.get("display_name") or _stock_name(e.get("code", ""))
            summ = (e.get("summary") or "").strip()
            lines.append(f"· {name}：{when} {label}" + (f"（{summ[:40]}）" if summ else ""))
        lines.append("")
    lines.append("详情见网页。")
    return "\n".join(lines)

