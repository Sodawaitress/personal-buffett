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


# ── US-193：行业集中度 ──────────────────────────────────

def test_concentration_handles_both_industry_formats():
    """stock_industry_map 存了两种格式：JSON（`{"name": "纺织服饰"}`）
    和裸字符串（`蓄电池及其他电池`）。只认一种会静默漏掉一半。"""
    import json as _j

    from radar_app.data.core import get_conn
    from scripts.pick_ledger import _industry_of
    with get_conn() as c:
        c.execute("DELETE FROM stock_industry_map WHERE code IN ('999001','999002')")
        c.execute("INSERT INTO stock_industry_map(code, industry) VALUES('999001', :i)",
                  {"i": _j.dumps({"label": "em:BK0436", "name": "纺织服饰"})})
        c.execute("INSERT INTO stock_industry_map(code, industry) "
                  "VALUES('999002', '蓄电池及其他电池')")
        assert _industry_of(c, "999001") == "纺织服饰"
        assert _industry_of(c, "999002") == "蓄电池及其他电池"
        assert _industry_of(c, "999999") is None
        c.execute("DELETE FROM stock_industry_map WHERE code IN ('999001','999002')")


def test_insufficient_industry_data_is_reported_not_guessed():
    """行业覆盖不到一半时，算出来的集中度没有意义 —— 说「数据不足」，
    不硬算一个好看的数字。"""
    from radar_app.data.core import get_conn
    from scripts.pick_ledger import concentration
    _fresh()
    with get_conn() as c:
        for i, code in enumerate(("990001", "990002", "990003")):
            c.execute("INSERT INTO pick_ledger(code,name,pick_date,reason_tags,updated_at)"
                      " VALUES(:c,:n,'2026-01-01','[]',CURRENT_TIMESTAMP)",
                      {"c": code, "n": f"测试{i}"})
    r = concentration("2026-01-01")
    assert r.get("insufficient") is True
    assert "top_pct" not in r


def test_concentration_flags_a_single_dominant_industry():
    """2026-08-28 实测：澜起（DDR5 接口）· 胜宏（AI-PCB）· 海光（国产 CPU）
    名字完全不同，但赚的是**同一条产业链**的钱。看起来买了 5 只，
    实际 3 只押同一件事 —— 一条砍单消息就能让它们一起跌。"""
    import json as _j

    from radar_app.data.core import get_conn
    from scripts.pick_ledger import concentration
    _fresh()
    plan = [("991001", "半导体"), ("991002", "半导体"), ("991003", "半导体"),
            ("991004", "稀土"), ("991005", "生物制品")]
    with get_conn() as c:
        c.execute("DELETE FROM stock_industry_map WHERE code LIKE '99100%'")
        for code, ind in plan:
            c.execute("INSERT INTO pick_ledger(code,name,pick_date,reason_tags,updated_at)"
                      " VALUES(:c,:c,'2026-01-02','[]',CURRENT_TIMESTAMP)", {"c": code})
            c.execute("INSERT INTO stock_industry_map(code,industry) VALUES(:c,:i)",
                      {"c": code, "i": _j.dumps({"name": ind})})
    r = concentration("2026-01-02")
    assert r["top_industry"] == "半导体" and r["top_pct"] == 0.6
    assert r["over_limit"] is True
    assert "60%" in r["warn"]
    assert r["has_defensive"] is True, "生物制品应算防御型"


def test_a_diversified_set_is_not_flagged():
    """这个检查**不禁止集中**，只让它可见。分散的组合不该报警。"""
    import json as _j

    from radar_app.data.core import get_conn
    from scripts.pick_ledger import concentration
    _fresh()
    plan = [("992001", "半导体"), ("992002", "稀土"), ("992003", "生物制品"),
            ("992004", "汽车"), ("992005", "机械")]
    with get_conn() as c:
        c.execute("DELETE FROM stock_industry_map WHERE code LIKE '99200%'")
        for code, ind in plan:
            c.execute("INSERT INTO pick_ledger(code,name,pick_date,reason_tags,updated_at)"
                      " VALUES(:c,:c,'2026-01-03','[]',CURRENT_TIMESTAMP)", {"c": code})
            c.execute("INSERT INTO stock_industry_map(code,industry) VALUES(:c,:i)",
                      {"c": code, "i": _j.dumps({"name": ind})})
    r = concentration("2026-01-03")
    assert r["over_limit"] is False
    assert r["warn"] == ""


def test_missing_defensive_is_also_flagged():
    """routine 要求「至少一只防御型」。全是周期/科技也该提醒。"""
    import json as _j

    from radar_app.data.core import get_conn
    from scripts.pick_ledger import concentration
    _fresh()
    plan = [("993001", "半导体"), ("993002", "稀土"), ("993003", "汽车"),
            ("993004", "机械"), ("993005", "有色金属")]
    with get_conn() as c:
        c.execute("DELETE FROM stock_industry_map WHERE code LIKE '99300%'")
        for code, ind in plan:
            c.execute("INSERT INTO pick_ledger(code,name,pick_date,reason_tags,updated_at)"
                      " VALUES(:c,:c,'2026-01-04','[]',CURRENT_TIMESTAMP)", {"c": code})
            c.execute("INSERT INTO stock_industry_map(code,industry) VALUES(:c,:i)",
                      {"c": code, "i": _j.dumps({"name": ind})})
    r = concentration("2026-01-04")
    assert r["has_defensive"] is False
    assert "没有防御型" in r["warn"]


def test_history_shows_repeated_concentration():
    """单看一天看不出问题 —— **连续几周押同一条线**才是真危险。"""
    from scripts.pick_ledger import concentration_history
    assert isinstance(concentration_history(3), list)


# ── US-194：台账标回股票页 ──────────────────────────────

def test_history_for_returns_nothing_for_unpicked_stock():
    from scripts.pick_ledger import history_for
    assert history_for("000000") == {}


def test_history_prefers_excess_over_raw_return():
    """绝对涨跌会被大盘带着走，说明不了选股本身
    （US-189：绝对 +1.2% 其实跑输大盘 +4%）。"""
    from radar_app.data.core import get_conn
    from scripts.pick_ledger import history_for
    _fresh()
    with get_conn() as c:
        c.execute("""INSERT INTO pick_ledger
            (code,name,pick_date,entry_price,advice,reason_tags,
             ret_5d,excess_5d,ret_10d,excess_10d,updated_at)
            VALUES('994001','测试','2026-01-05',10,'机构调研密集','["机构调研"]',
                   5.0,2.0,8.0,3.5,CURRENT_TIMESTAMP)""")
    h = history_for("994001")
    assert h["count"] == 1
    it = h["items"][0]
    assert it["horizon"] == 10, "有 10 日结果时优先报更长的持有期"
    assert it["excess"] == 3.5
    assert h["avg_excess"] == 3.5
    assert it["tags"] == ["机构调研"]


def test_history_survives_unresolved_picks():
    """还没出结果的推荐也要显示 —— 用户要知道「推荐过但还在等」。"""
    from radar_app.data.core import get_conn
    from scripts.pick_ledger import history_for
    _fresh()
    with get_conn() as c:
        c.execute("""INSERT INTO pick_ledger(code,name,pick_date,reason_tags,updated_at)
                     VALUES('994002','测试2','2026-01-06','[]',CURRENT_TIMESTAMP)""")
    h = history_for("994002")
    assert h["count"] == 1 and h["resolved"] == 0
    assert h["avg_excess"] is None
    assert h["items"][0]["excess"] is None


def test_stock_page_renders_pick_history():
    import db
    db.init_db()
    from app import app

    from scripts.pick_ledger import ingest, seed_history
    seed_history()
    ingest()
    from scripts.pick_ledger import history_for
    mine = set(db.get_user_holdings(1) or []) | set(db.get_user_watching(1) or [])
    cand = [c for c in mine if history_for(c)]
    if not cand:
        return                                  # 本地没有交集就跳过
    app.config['TESTING'] = True
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['user_id'] = 1
    h = cl.get(f'/stock/{cand[0]}/signals').get_data(as_text=True)
    assert 'class="pickhist"' in h
    assert '被推荐过' in h


def test_page_explains_what_excess_means():
    """「超额」是个专业词，用户不会自动知道它是什么。
    必须在同一处解释清楚 —— 这是本仓一贯的做法（US-176 的教训）。"""
    tpl = open(os.path.join(ROOT, 'templates', 'stock', 'signals.html'),
               encoding='utf-8').read()
    # 块内有嵌套 {% if %}，不能拿第一个 {% endif %} 当结尾
    # （这个坑本仓踩到第三次了 —— US-180 的测试也栽过）
    seg = tpl[tpl.index('class="pickhist"'):tpl.index('US-179/180 信息传导链')]
    assert '减去' in seg and '同期' in seg, "要说清超额是怎么算的"
    assert '不经人工' in seg or '自动回填' in seg, "要说清结果不是人写的"
