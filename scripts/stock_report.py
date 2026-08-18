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

def _early_warnings_for(codes, days=14):
    """每股取一条 is_early 的重大动向。

    US-160：加日期窗口。原来 get_stock_events 取最近 20 条**不做任何日期过滤**，
    于是一个月前的预警也会被当成「今天该注意的」天天推 —— 这是「每天推送
    内容一样」的原因之一。
    """
    import json
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for code in codes:
        for e in (_db.get_stock_events(code) or []):
            if e.get("source") != "news_material":
                continue
            if str(e.get("event_date") or "")[:10] < cutoff:
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
                             date_str: str, commit: bool = True) -> str:
    """兼容旧签名：只要正文。commit=True 时立即记账。

    **推荐用 build_user_push_payload()** —— 它把「算内容」和「记账」分开，
    这样干跑不会吃掉条目、发送失败也不会把条目永久吞掉。
    """
    content, pending = build_user_push_payload(user_id, date_str)
    if commit and content:
        from radar_app.data.push_ledger import commit_pushed
        commit_pushed(user_id, pending)
    return content


def build_user_push_payload(user_id: int, date_str: str):
    """今天该**变化**了的（US-160 改写自 US-123）。返回 (正文, 待记账条目)。

    原来标题写「今天该注意的」，但五个板块里有四个取的是**当前状态**，
    不是今日事件：早期预警无日期过滤、机构结论/脚印是当前值、催化剂是
    未来 7 天窗口 —— 同一件事会连播多天。而系统此前没有任何去重机制，
    结果就是「每天推送内容几乎一样」，用户很快就不看了。

    现在每个条目都带 (身份, 状态)：身份首次出现、或身份还在但状态变了，
    才进推送。没变的折叠成一行「另有 N 项与上次相同」——让人知道系统
    还活着，而不是以为它死了。

    commit=False 用于预览/测试：算出内容但不写台账。
    """
    from radar_app.data.push_ledger import filter_changed, state_hash

    holdings = _db.get_user_holdings(user_id) or []
    watching = _db.get_user_watching(user_id) or []
    codes = list(dict.fromkeys(list(holdings) + list(watching)))
    if not codes:
        return "", []

    # ── 收集候选：(section, item_key, state_hash, 正文行) ──
    cand = []

    for code, d in _early_warnings_for(codes):
        tail = "（市场还没反应，你早）" if d.get("market_status") == "not_priced" else ""
        text = d.get("explain") or d.get("title", "")
        cand.append(("early", f"early:{code}", state_hash(text),
                     f"· {_stock_name(code)}：{text}{tail}"))

    for code, conclusion, is_lead in _signal_leads_for(codes):
        badge = "⚡ " if is_lead else ""
        cand.append(("lead", f"lead:{code}", state_hash(conclusion, is_lead),
                     f"· {badge}{_stock_name(code)}：{conclusion}"))

    for code, direction in _prophet_dirs_for(codes):
        word = "在悄悄建仓" if direction == "rising" else "在陆续离场"
        cand.append(("prophet", f"prophet:{code}", state_hash(direction),
                     f"· {_stock_name(code)}：机构{word}"))

    for code, old_g, new_g in _grade_changes_for(codes):
        arrow = "↑" if _grade_rank(new_g) < _grade_rank(old_g) else "↓"
        cand.append(("grade", f"grade:{code}", state_hash(old_g, new_g),
                     f"· {_stock_name(code)}：{old_g} → {new_g} {arrow}"))

    for e in _catalysts_for(user_id):
        label = _CATALYST_LABEL.get(e.get("event_type"), "事件")
        du = e.get("days_until")
        when = "今天" if du == 0 else f"{du}天后"
        name = e.get("display_name") or _stock_name(e.get("code", ""))
        summ = (e.get("summary") or "").strip()
        # 身份含事件日期 → 同一件事只推一次；状态分「临近(≤1天)」和「还早」
        # → 临近时会因状态变化再提醒一次，这是有价值的重复，不是噪音。
        key = f"catalyst:{e.get('code','')}:{e.get('event_type','')}:{e.get('event_date','')}"
        cand.append(("catalyst", key, state_hash("imminent" if (du or 9) <= 1 else "far"),
                     f"· {name}：{when} {label}" + (f"（{summ[:40]}）" if summ else "")))

    if not cand:
        return "", []

    changed, unchanged = filter_changed(user_id, [(k, h, (sec, line))
                                                  for sec, k, h, line in cand])
    if not changed:
        return "", []   # 全是老面孔 —— 不打扰

    by_sec = {}
    for _, _, (sec, line) in changed:
        by_sec.setdefault(sec, []).append(line)

    lines = [f"📌 今天有变化的 · {date_str}", ""]
    for sec, title, cap in (("early", "🔔 早期预警", 6),
                            ("lead", "🛰️ 机构领先信号", 6),
                            ("prophet", "🧭 机构脚印", 6),
                            ("grade", "📊 评级变化", 8),
                            ("catalyst", "📅 催化剂预警", 6)):
        rows = by_sec.get(sec) or []
        if not rows:
            continue
        lines.append(f"{title}（{len(rows)}）")
        lines.extend(rows[:cap])
        lines.append("")

    if unchanged:
        lines.append(f"（另有 {unchanged} 项与上次推送相同，未重复列出）")
        lines.append("")
    lines.append("详情见网页。")

    # 记账交给调用方：干跑不该吃掉条目，发送失败也不该把条目永久吞掉
    return "\n".join(lines), changed

