"""US-171：推送内容的取数从「每只查一次」改成批量。

## 事故

push-svc 2026-08-25 撞上 20 分钟超时被杀，**妈妈那天的信一个字都没发出去**。
GitHub 把超时记成 `cancelled`，看起来像有人手动取消，不像故障。

历史耗时：08-21 **3 分钟** → 08-24 **18 分钟** → 当晚 **超 20 分钟**。
涨的原因是 US-162 把妈妈那 198 只自选股并进了日报候选。

## 根因不是算法，是往返次数

每只股票约 8.3 条 SQL，231 只 ≈ 1900 条。而 Neon 开了 `pool_pre_ping`
（serverless scale-to-zero 会断闲置连接，不探活就 SSL SYSCALL 报错），
**每次 get_conn 都额外发一条 SELECT 1** —— 实际约 3800 次跨洋往返。
GHA 美国 runner ↔ Neon 单程几百毫秒，乘起来正好十几分钟。

**本地 SQLite 上完全看不出来**（往返几乎免费，全量 90 只只要 0.7 秒）——
这正是它能悄悄长到 18 分钟没人发现的原因。同一个教训：
性能问题和数据问题一样，本地测不出生产。

## 做法

把「N 只各查一次」压成「一条 IN 查询」。算法一行没改，只改取数。
实测每只 8.3 → 1.13 条，领先信号那段 401 → 5 条。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db  # noqa: E402


def _codes(n=None):
    db.init_db()
    c = list(dict.fromkeys((db.get_user_holdings(1) or [])
                           + (db.get_user_watching(1) or [])))
    return c[:n] if n else c


def _count_sql(fn, *a, **k):
    from sqlalchemy import event

    from radar_app.data.core import get_engine
    n = {'q': 0}

    def _c(*_a):
        n['q'] += 1
    event.listen(get_engine(), "before_cursor_execute", _c)
    try:
        out = fn(*a, **k)
    finally:
        event.remove(get_engine(), "before_cursor_execute", _c)
    return out, n['q']


# ── 批量取数不改变结果 ──────────────────────────────────

def test_prefetched_conclusions_are_identical():
    """最重要的一条：预取只能更快，**不能改变任何一个字**。
    否则同一只股票在推送里和详情页会讲两套话。"""
    import radar_app.data.signal_events as se
    codes = _codes(40)
    se.clear_prefetch()
    plain = {c: se.get_signal_conclusion(c) for c in codes}
    se.prefetch_for(codes)
    cached = {c: se.get_signal_conclusion(c) for c in codes}
    se.clear_prefetch()
    assert plain == cached, [c for c in codes if plain[c] != cached[c]][:5]


def test_batched_helpers_match_per_code_versions():
    import json
    from datetime import date, timedelta

    import scripts.stock_report as sr
    codes = _codes()
    cutoff = (date.today() - timedelta(days=14)).strftime("%Y-%m-%d")

    old = []
    for code in codes:
        for e in (db.get_stock_events(code) or []):
            if e.get("source") != "news_material":
                continue
            if str(e.get("event_date") or "")[:10] < cutoff:
                continue
            try:
                d = json.loads(e.get("detail_json") or "{}")
            except Exception:
                continue
            if d.get("is_early"):
                old.append(code)
                break
    assert set(old) == {c for c, _ in sr._early_warnings_for(codes)}

    old_g = []
    for code in codes:
        h = db.get_analysis_history(code, period="daily", limit=2) or []
        if len(h) >= 2:
            n, o = h[0].get("grade"), h[1].get("grade")
            if n and o and n != o:
                old_g.append((code, o, n))
    assert set(old_g) == set(sr._grade_changes_for(codes))


def test_bulk_names_match_single_lookup():
    import scripts.stock_report as sr
    codes = _codes(30)
    bulk = sr._bulk_stock_names(codes)
    sr._reset_caches()
    assert all(bulk[c] == sr._stock_name(c) for c in codes)


# ── 往返次数不许再涨回去 ────────────────────────────────

def test_payload_build_stays_under_two_queries_per_stock():
    """守的是**往返次数**，不是墙钟时间 —— 本地 SQLite 上时间永远好看，
    生产上决定生死的是往返次数。

    改前 8.3 条/只。阈值定在 2.0：留出余量给新信号，但任何人再写一个
    逐只查库的 helper 都会立刻顶破它。
    """
    import scripts.stock_report as sr
    codes = _codes()
    assert len(codes) >= 20, "样本太小，这条测试没有意义"
    _, q = _count_sql(sr.build_user_push_payload, 1, "2026-08-25")
    per = q / len(codes)
    assert per < 2.0, (
        f"每只 {per:.2f} 条 SQL（{q} 条 / {len(codes)} 只）—— 231 只时会重回"
        f"超时区间，妈妈的信会丢")


def test_signal_leads_does_not_query_per_stock():
    import scripts.stock_report as sr
    codes = _codes()
    _, q = _count_sql(sr._signal_leads_for, codes)
    assert q < len(codes) / 4, f"领先信号 {q} 条 SQL / {len(codes)} 只 —— 预取没生效"


# ── 缓存必须是显式的，不能悄悄长效 ──────────────────────

def test_prefetch_is_opt_in_and_cleared():
    """单只查询（详情页）绝不能走缓存 —— 那会把上一次批处理的旧数据
    带到用户面前。默认 None = 走原路径。"""
    import radar_app.data.signal_events as se
    se.clear_prefetch()
    assert se._cached("precursor", "000001") is se._MISS
    se.prefetch_for(["000001"])
    assert se._cached("precursor", "000002") is se._MISS, "不在本批里的必须 MISS"
    se.clear_prefetch()
    assert se._cached("precursor", "000001") is se._MISS, "clear 之后必须失效"


def test_signal_leads_clears_prefetch_after_itself():
    import radar_app.data.signal_events as se
    import scripts.stock_report as sr
    sr._signal_leads_for(_codes(10))
    assert se._cached("precursor", _codes(1)[0]) is se._MISS, \
        "批处理结束必须清缓存，否则同进程的网页请求会读到陈旧数据"


def test_name_cache_is_reset_per_build():
    import scripts.stock_report as sr
    sr._NAME_CACHE["FAKE"] = "过期的名字"
    sr.build_user_push_payload(1, "2026-08-25")
    assert "FAKE" not in sr._NAME_CACHE, "每次 build 应重置名字缓存"
