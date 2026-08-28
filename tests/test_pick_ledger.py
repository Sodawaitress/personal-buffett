"""US-192：五选台账 —— Claude 写不了自己的成绩单。

## 起因

用户要看五选准确度，**调不出来**（US-189）：`picks_open.json` 只记
「推荐了什么」不记结果，历史散落在推送正文里，算一次要靠 git 考古。

而临时算出来那次（35 条、胜率 68.6%、平均 +1.2%）有三个致命缺陷：

    没有基准    同期大盘 +4%，绝对 +1.2% 其实**跑输**
    持有期不齐  08-11 推荐的算 16 天，08-26 的只算 1 天
    样本重复    35 条只覆盖约 15 只（002415 被选 4 次）

## 关键设计：职责分离

五选是 **Claude 在每日 routine 里人工判断**选出来的，不是算法。
所以 US-189 那次评估是「我给我自己打分」——结构性的利益冲突。

    Claude（routine 定时任务）  →  只写 picks_open.json
    流水线（svc_digest，纯代码）→  落账 + 回填 + 算超额   ← Claude 碰不到
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _fresh():
    import db
    db.init_db()
    from radar_app.data.core import get_conn
    with get_conn() as c:
        c.execute("DELETE FROM pick_ledger")


# ── 落账 ────────────────────────────────────────────────

def test_ingest_reads_picks_and_locks_entry_price():
    from radar_app.data.core import get_conn
    from scripts.pick_ledger import ingest
    _fresh()
    r = ingest()
    assert r["added"] > 0, r
    with get_conn() as c:
        row = c.execute("SELECT * FROM pick_ledger LIMIT 1").fetchone()
    assert row["pick_date"] and len(row["pick_date"]) == 10


def test_ingest_never_overwrites():
    """落账价一旦锁定就不能再动 —— 否则成绩单可以被事后修饰。"""
    from scripts.pick_ledger import ingest
    _fresh()
    a = ingest()
    b = ingest()
    assert b["added"] == 0 and b["skipped"] == a["added"]


def test_history_seed_is_idempotent():
    from scripts.pick_ledger import seed_history
    _fresh()
    a = seed_history()
    b = seed_history()
    assert a["added"] == 25 and b["added"] == 0


# ── 理由分类：台账最有价值的一列 ────────────────────────

def test_reasons_are_tagged():
    """三个月后要能回答「我哪一类理由准」—— 某类长期不准，
    那类信号就该从五选依据里拿掉。"""
    from scripts.pick_ledger import _tag_reasons
    assert "机构调研" in _tag_reasons({"advice": "近期机构密集调研，值得关注"})
    assert "估值" in _tag_reasons({"advice": "估值处于历史低位"})
    t = _tag_reasons({"advice": "主力资金持续流入，且融券在减少"})
    assert "资金流入" in t and "融券变化" in t


def test_untaggable_advice_returns_empty_not_a_fake_tag():
    from scripts.pick_ledger import _tag_reasons
    assert _tag_reasons({"advice": "继续观察"}) == []
    assert _tag_reasons({}) == []


# ── 回填：只算交易日 ────────────────────────────────────

def test_horizons_are_trading_days_not_calendar_days():
    """「5 日」必须是 5 个**有价格的交易日**。用自然日会把周末算进去，
    不同推荐日的持有期就不可比 —— 那正是 US-189 那次评估的缺陷之一。"""
    src = open(os.path.join(ROOT, 'scripts', 'pick_ledger.py'), encoding='utf-8').read()
    fn = src[src.index('def _trading_days_after'):src.index('def _bench_between')]
    assert 'ORDER BY d ASC LIMIT :n' in fn
    assert 'if len(rows) < n' in fn, "不足 n 个交易日必须返回 None，不能凑数"


def test_benchmark_sums_daily_averages_not_endpoint_prices():
    """池子里每天有价的股票不完全相同，用首尾价格比会失真。
    必须逐日 AVG(change_pct) 再累加。"""
    src = open(os.path.join(ROOT, 'scripts', 'pick_ledger.py'), encoding='utf-8').read()
    fn = src[src.index('def _bench_between'):src.index('def backfill')]
    assert 'AVG(change_pct)' in fn
    assert 'COUNT(DISTINCT code) >= 30' in fn, "样本太少的日子不能当基准"


# ── 成绩单报超额，不报绝对胜率 ──────────────────────────

def test_scorecard_reports_excess_not_raw_win_rate():
    """没有基准的胜率会误导 —— US-189：绝对 +1.2% 其实跑输大盘 +4%。"""
    from scripts.pick_ledger import scorecard
    s = scorecard(10)
    assert "avg_excess" in s and "beat_bench" in s
    assert "win_rate" not in s, "不报绝对胜率"


def test_scorecard_breaks_down_by_reason():
    from scripts.pick_ledger import scorecard
    assert "by_reason" in scorecard(10)


# ── 职责分离 ────────────────────────────────────────────

def test_backfill_runs_in_the_pipeline_not_the_routine():
    """五选是 Claude 的判断，成绩单必须由代码算。
    如果回填被搬进 routine，这条会红。"""
    dg = open(os.path.join(ROOT, 'scripts', 'svc_digest.py'), encoding='utf-8').read()
    assert 'from scripts.pick_ledger import backfill' in dg
    routine = open(os.path.join(ROOT, 'CLAUDE_ROUTINE.md'), encoding='utf-8').read()
    assert 'pick_ledger' not in routine, \
        "routine 不该碰台账 —— Claude 只写 picks_open.json"


def test_ledger_failure_does_not_break_the_snapshot():
    dg = open(os.path.join(ROOT, 'scripts', 'svc_digest.py'), encoding='utf-8').read()
    seg = dg[dg.index('US-192 五选台账'):]
    seg = seg[:seg.index('US-155')]
    assert 'except Exception' in seg and '不影响快照' in seg
