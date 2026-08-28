"""US-196/197：今日五选做成网站上的一页，并带着历史战绩。

## 起因

用户妈妈：「我这个是里面逃出来的这么多股票，然后这个网站又慢，
**有的信息就错过了**」。

而用户点破了关键：**「今日有什么值得看」不就是我们的今日五选** ——
问题不是要再造一个汇总页，是**五选只活在微信推送和 git 里，
网站上完全看不到**。微信一刷就过去了，回头找不着。

用户还指定了要哪种「验证」：**验证 routine 说得对不对** ——
把台账的结果标回五选页，**每条推荐旁边就是它上次的成绩**。
如果某只反复被选中却反复跑输，一眼就看得出来。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')

SAMPLE = """【今日五选】2026-08-28

📅 本文基于 2026-08-27（周四）收盘数据。

━━ 今日主题 ━━
AI 硬件全链条继续放量。

━━ 1/澜起科技 (688008) +10.06% ━━
[公司底] DDR5 内存接口芯片全球寡头。
[机构] 30 天 2 次特定对象调研。
[大众] 散户已在关注。
今天的判断：趋势确认，空间被估值消耗。
操作提示：不追高，等回调到 ¥200 附近。

━━ 2/海光信息 (688041) +6.50% · 新入库 · 入门鉴定 ━━
[公司底] 国产 x86 CPU 龙头。
[机构] 30 天 1 次特定对象调研。
[大众] 认知度显著低于寒武纪。
今天的判断：最理想的进场窗口。
操作提示：¥235–¥240 分批建仓 30%，止损 ¥220。
"""


# ── 解析 ────────────────────────────────────────────────

def test_parses_the_real_format():
    from radar_app.picks.parser import parse
    d = parse(SAMPLE)
    assert d["date"] == "2026-08-28"
    assert len(d["items"]) == 2
    a, b = d["items"]
    assert (a["code"], a["name"], a["change"]) == ("688008", "澜起科技", "+10.06%")
    assert b["badge"] == "新入库 · 入门鉴定"
    assert set(a["layers"]) == {"公司底", "机构", "大众"}
    assert "趋势确认" in a["verdict"]
    assert "不追高" in a["action"]


def test_unparseable_returns_empty_not_garbage():
    """正文是人（Claude）写的自由文本，格式可能变。
    **页面上宁可显示「今天的五选还没生成」，也不要显示半截错乱的内容** ——
    后者会让人以为系统坏了，或者把残缺分析当成完整判断。"""
    from radar_app.picks.parser import parse
    assert parse("") == {}
    assert parse("服务器数据未刷新，今日无分析。请以券商 APP 为准") == {}
    assert parse("【今日五选】没有日期") == {}
    assert parse("【今日五选】2026-08-28\n只有标题没有条目") == {}


def test_parse_file_missing_is_safe():
    from radar_app.picks.parser import parse_file
    assert parse_file("output/definitely-not-here.txt") == {}


# ── 验证「对不对」：每条带历史战绩 ──────────────────────

def test_each_pick_carries_its_track_record():
    """用户要的验证是这个：把台账结果标回五选页。
    结果全部来自 pick_ledger，由流水线自动回填（US-192），Claude 碰不到。"""
    import db
    db.init_db()
    from radar_app.data.core import get_conn

    from radar_app.picks.service import build
    with get_conn() as c:
        c.execute("DELETE FROM pick_ledger WHERE code='688008'")
        c.execute("""INSERT INTO pick_ledger
            (code,name,pick_date,entry_price,reason_tags,ret_10d,excess_10d,updated_at)
            VALUES('688008','澜起科技','2026-08-01',100,'[]',5.0,2.5,CURRENT_TIMESTAMP)""")
    tmp = "/tmp/_pick_sample.txt"
    open(tmp, "w", encoding="utf-8").write(SAMPLE)
    doc = build(tmp)
    hit = [i for i in doc["items"] if i["code"] == "688008"][0]
    assert hit["history"]["count"] >= 1
    assert hit["history"]["avg_excess"] == 2.5


def test_page_shows_record_and_says_it_is_automatic():
    tpl = open(os.path.join(ROOT, 'templates', 'picks.html'), encoding='utf-8').read()
    assert 'pick-record' in tpl and '过往战绩' in tpl
    assert '不经人工' in tpl, "用户需要知道成绩单不是 Claude 写的"


def test_page_explains_what_excess_means():
    """「超额」是专业词，必须在同一处解释（US-176 的教训：
    术语要在它出现的地方消解）。"""
    tpl = open(os.path.join(ROOT, 'templates', 'picks.html'), encoding='utf-8').read()
    assert '减去' in tpl and '同期自选池' in tpl


# ── 打通：五选页 ↔ 股票页 ───────────────────────────────

def test_each_pick_links_to_the_stock_page():
    tpl = open(os.path.join(ROOT, 'templates', 'picks.html'), encoding='utf-8').read()
    assert '/stock/{{ it.code }}/signals' in tpl


def test_nav_has_an_entry():
    base = open(os.path.join(ROOT, 'templates', 'base.html'), encoding='utf-8').read()
    assert '/picks' in base and '今日五选' in base


# ── 集中度也带到这一页 ──────────────────────────────────

def test_concentration_warning_appears_on_the_page():
    """名字不同 ≠ 篮子不同（US-193）。五选页是最该看到这条的地方。"""
    tpl = open(os.path.join(ROOT, 'templates', 'picks.html'), encoding='utf-8').read()
    assert 'picks-conc' in tpl
    assert '不把鸡蛋放一个篮子' in tpl


# ── 端到端 ──────────────────────────────────────────────

def test_page_renders():
    import db
    db.init_db()
    from app import app
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 1
    r = c.get('/picks')
    assert r.status_code == 200
    assert '今日五选' in r.get_data(as_text=True)


def test_stale_picks_are_flagged():
    """五选是哪天的必须说清楚 —— 微信里看不出，网站上更要标。"""
    tpl = open(os.path.join(ROOT, 'templates', 'picks.html'), encoding='utf-8').read()
    assert 'picks-stale' in tpl and '今天还没更新' in tpl
