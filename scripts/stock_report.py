"""Report and push-content builders extracted from stock_pipeline."""

import os
import db as _db

# US-168：等级顺序全站只有一份，见 radar_app/watchlist/presenter.py
from radar_app.watchlist.presenter import grade_rank as _grade_rank


# ── US-171：批量取数，替掉逐只查库 ──────────────────────────────────────
#
# push-svc 从 3 分钟涨到 18 分钟，2026-08-25 首次撞上 20 分钟上限被杀，
# **妈妈那天的信一个字都没发出去**。
#
# 原因不是 Python 慢，是**往返次数**：每只股票约 8 条 SQL，妈妈 231 只
# → 约 1900 条。而 Neon 开了 pool_pre_ping（scale-to-zero 会断闲连接，
# 不探活就 SSL SYSCALL 报错），**每次 get_conn 都额外发一条 SELECT 1**，
# 于是实际约 3800 次往返。GHA 美国 runner ↔ Neon 单程几百毫秒，
# 乘起来正好十几分钟。
#
# 所以优化的对象是「查库次数」，不是算法。下面几个 _bulk_* 把
# 「N 只股票各查一次」压成「一条 IN 查询」。
# 本地 SQLite 上看不出差别（往返几乎免费）—— 这正是它能长到 18 分钟
# 没人发现的原因。

def _chunks(seq, n=400):
    """IN 列表分批：Postgres 参数上限 65535，留足余量。"""
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _bulk_stock_names(codes) -> dict:
    """一次取回所有股票名。原来每只一条 SELECT。"""
    from radar_app.data.core import get_conn
    out = {}
    for part in _chunks(codes):
        keys = {f"c{i}": c for i, c in enumerate(part)}
        ph = ",".join(f":{k}" for k in keys)
        with get_conn() as c:
            for r in c.execute(
                    f"SELECT code, name_cn, name FROM stocks WHERE code IN ({ph})", keys):
                out[r["code"]] = r["name_cn"] or r["name"] or r["code"]
    return {c: out.get(c, c) for c in codes}


def _bulk_recent_events(codes, days=14) -> dict:
    """一次取回所有股票近 N 天的 news_material 事件，按 code 分组。"""
    from datetime import date, timedelta

    from radar_app.data.core import get_conn
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    for part in _chunks(codes):
        keys = {f"c{i}": c for i, c in enumerate(part)}
        ph = ",".join(f":{k}" for k in keys)
        with get_conn() as c:
            rows = c.execute(
                f"""SELECT code, event_date, detail_json FROM stock_events
                    WHERE code IN ({ph}) AND source = 'news_material'
                      AND event_date >= :cut
                    ORDER BY event_date DESC, id DESC""",
                {**keys, "cut": cutoff}).fetchall()
        for r in rows:
            out.setdefault(r["code"], []).append(dict(r))
    return out


def _bulk_last_two_grades(codes, period="daily") -> dict:
    """一次取回每只最近两条评级。窗口函数在 SQLite ≥3.25 和 PG 都支持，
    但这里用最朴素的办法（取全部再在 Python 里截断），少一层方言风险。"""
    from radar_app.data.core import get_conn
    out = {}
    for part in _chunks(codes):
        keys = {f"c{i}": c for i, c in enumerate(part)}
        ph = ",".join(f":{k}" for k in keys)
        with get_conn() as c:
            rows = c.execute(
                f"""SELECT code, grade, analysis_date FROM analysis_results
                    WHERE code IN ({ph}) AND period = :p
                    ORDER BY code, analysis_date DESC""",
                {**keys, "p": period}).fetchall()
        for r in rows:
            lst = out.setdefault(r["code"], [])
            if len(lst) < 2:
                lst.append(r["grade"])
    return out


# US-171：一次推送里同一只股票的名字会被查好几遍（早期预警、领先信号、
# 预言线、评级变化各一次）。缓存只在一次 build 内有效，由 _prime_names()
# 装载、_reset_caches() 清空 —— 不做全局长效缓存，改了名当天就能反映出来。
_NAME_CACHE: dict = {}


def _prime_names(codes):
    _NAME_CACHE.update(_bulk_stock_names(codes))


def _reset_caches():
    _NAME_CACHE.clear()


def _stock_name(code):
    if code in _NAME_CACHE:
        return _NAME_CACHE[code]
    s = _db.get_stock(code) or {}
    name = s.get("name_cn") or s.get("name") or code
    _NAME_CACHE[code] = name
    return name

def _early_warnings_for(codes, days=14):
    """每股取一条 is_early 的重大动向。

    US-160：加日期窗口。原来 get_stock_events 取最近 20 条**不做任何日期过滤**，
    于是一个月前的预警也会被当成「今天该注意的」天天推 —— 这是「每天推送
    内容一样」的原因之一。

    US-171：改批量取数。原来每只一条 SELECT，231 只就是 231 次往返
    （Neon 上再乘 pre_ping 的 SELECT 1）。
    """
    import json
    out = []
    by_code = _bulk_recent_events(codes, days=days)
    for code in codes:
        for e in by_code.get(code, []):
            try:
                d = json.loads(e.get("detail_json") or "{}")
            except Exception:
                continue
            if d.get("is_early"):
                out.append((code, d))
                break
    return out


def _grade_changes_for(codes):
    """US-171：批量取数，原来每只一条 get_analysis_history。"""
    out = []
    by_code = _bulk_last_two_grades(codes)
    for code in codes:
        hist = by_code.get(code) or []
        if len(hist) >= 2:
            new_g, old_g = hist[0], hist[1]
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
    """机构领先信号（US-123）：每股一句结论，只留 lead 或 high confidence 的。

    US-171：先 prefetch_for 一次把这批股票的前兆/资金流/基本面/价格全取回来，
    再逐只算结论 —— 算法不变，往返次数从每只 4~5 次降到整批 5 次。
    """
    try:
        from radar_app.data.signal_events import (clear_prefetch,
                                                  get_signal_conclusion,
                                                  prefetch_for)
    except Exception:
        return []
    try:
        prefetch_for(codes)
    except Exception:
        clear_prefetch()      # 预取失败就走原路径，慢但不错
    out = []
    for code in codes:
        try:
            sc = get_signal_conclusion(code)
        except Exception:
            sc = None
        if sc and (sc.get("lead") or sc.get("confidence") == "high") and sc.get("conclusion"):
            out.append((code, sc["conclusion"], bool(sc.get("lead"))))
    clear_prefetch()
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


def digest_user_ids(primary: int) -> list:
    """这份日报要覆盖谁的自选股（US-162）。

    背景：推送只有**一个收件人**（全局 Server酱 key），但候选股票来自
    `admin_user_id()` 一个账号。生产实测发现错配 —— 妈妈的实际自选股
    198 只在 id=2（QQ 账号）上，而 admin(id=4) 只有 33 只，所以那 198 只
    **从来没进过每日「今天有变化的」推送**（她只在五选信里被覆盖，
    因为快照的 scope 是 all_users）。

    用环境变量声明而不是硬编码 id：改覆盖范围不用改代码。
    默认只有 primary，保持原行为。
    """
    ids = [primary]
    raw = os.environ.get("DIGEST_USER_IDS", "")
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids


def build_user_push_payload(user_id: int, date_str: str, extra_user_ids=()):
    """今天该**变化**了的（US-160 改写自 US-123）。返回 (正文, 待记账条目)。

    `extra_user_ids`：额外并入候选股票的账号（US-162）。台账仍记在
    `user_id` 名下 —— 台账跟的是**收件人**（谁被打扰过），不是股票的主人。

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

    codes = []
    for uid in [user_id, *extra_user_ids]:
        codes.extend(_db.get_user_holdings(uid) or [])
        codes.extend(_db.get_user_watching(uid) or [])
    codes = list(dict.fromkeys(codes))
    if not codes:
        return "", []

    # US-171：先一次性把名字取回来。这一份 payload 里同一只股票的名字
    # 会被查四五遍，逐只查在 Neon 上就是四五次跨洋往返。
    _reset_caches()
    _prime_names(codes)

    # ── 收集候选：(section, item_key, state_hash, 正文行) ──
    cand = []

    # US-178：「市场还没反应，你早」说的是**事件当天**市场没异动（AR z 值），
    # 但 _early_warnings_for 的窗口是 **14 天** —— 一条 13 天前的新闻会带着
    # 这句话出现在「今天有变化的」里，而这 13 天市场早就反应完了。
    # 而且推送里**不显示日期**，读的人根本不知道这是哪天的事。
    #
    # 和 US-177 是同一个病（把过去的观测讲成现在的状态），只是这次
    # 越界的是「事件日」和「今天」之间那段距离。
    from datetime import date as _date
    for code, d in _early_warnings_for(codes):
        ev_date = str(d.get("date") or d.get("event_date") or "")[:10]
        age = None
        try:
            age = (_date.today() - _date.fromisoformat(ev_date)).days
        except (ValueError, TypeError):
            age = None
        if d.get("market_status") == "not_priced":
            if age is None:
                tail = "（当时市场没反应）"
            elif age <= 1:
                tail = "（市场还没反应，你早）"
            else:
                # 隔了几天就只能说「当天」，不能再说「还没」
                tail = f"（{age} 天前的消息，**当天**市场没反应）"
        else:
            tail = ""
        text = d.get("explain") or d.get("title", "")
        cand.append(("early", f"early:{code}", state_hash(text, tail),
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

