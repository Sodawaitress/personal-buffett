"""US-168：自选页排序 / 筛选规则梳理。

起因是用户看着自选页问「这些筛选真的有用吗」。查下来：**生产上一个都没用。**

`/api/watchlist/filter` 的子查询是
    SELECT code, grade, MAX(id) AS id FROM analysis_results GROUP BY code
`grade` 既不在 GROUP BY 里也没被聚合。SQLite 容忍（随便挑一行，还不保证
是 MAX(id) 那行），Postgres 直接报错。而这个 LEFT JOIN 是**无条件**拼进
基础 query 的，所以市场筛选也一起死。前端 fetch 没有 try/catch，异常一抛
函数就断在半路 —— 按钮点了毫无反应，两年没人知道坏了。

本地测不出来。是 audit-svc 在生产上探到的：
    现役 GROUP BY 子查询: FAILS: column "analysis_results.grade" must
    appear in the GROUP BY clause or be used in an aggregate function
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ── 等级词汇表只有一份 ──────────────────────────────────

def test_grade_order_knows_a_plus():
    """A+ 以前有筛选按钮，但 GRADE_ORDER 不认识它 → grade_sort=99 →
    真出现 A+ 会被「按等级排序」排到最底。比幽灵按钮更糟。"""
    from radar_app.watchlist.presenter import GRADE_ORDER, grade_rank
    assert "A+" in GRADE_ORDER
    assert grade_rank("A+") < grade_rank("A") < grade_rank("D")


def test_grade_order_covers_every_grade_the_pipeline_can_emit():
    from radar_app.watchlist.presenter import GRADE_ORDER
    for g in ("A+", "A", "B+", "B", "B-", "C+", "C", "D", "D-"):
        assert g in GRADE_ORDER, f"{g} 会被排到最后"


def test_unknown_grade_sorts_last_never_first():
    from radar_app.watchlist.presenter import grade_rank
    assert grade_rank(None) == 99
    assert grade_rank("") == 99
    assert grade_rank("鬼画符") == 99


def test_only_one_grade_vocabulary_in_the_repo():
    """曾经有三套：模板一套、presenter 一套、stock_report 一套。"""
    assert "_GRADE_ORDER = [" not in _read('scripts/stock_report.py')
    assert "from radar_app.watchlist.presenter import grade_rank" in \
        _read('scripts/stock_report.py')


# ── 那条会在 Postgres 炸掉的查询 ────────────────────────

def test_no_bare_column_groupby_in_filter_query():
    """裸列 GROUP BY 在 SQLite 静默通过、在 Postgres 报错 —— 是本仓
    「本地绿灯、生产爆炸」的典型。"""
    src = _read('radar_app/watchlist/routes.py')
    assert "MAX(id) AS id\n                FROM analysis_results GROUP BY code" not in src
    assert re.search(r"a\.id\s*=\s*\(SELECT MAX\(r\.id\)", src), \
        "应按主键关联最新一行，两种数据库行为一致"


def test_filter_endpoint_reports_errors_instead_of_dying_silently():
    """静默 500 正是这个 bug 藏这么久的原因。"""
    src = _read('radar_app/watchlist/routes.py')
    seg = src[src.index('def api_watchlist_filter'):]
    seg = seg[:seg.index('@app.route', 10)] if '@app.route' in seg[10:] else seg
    assert 'except Exception' in seg and '500' in seg


# ── 筛选按钮不写死 ──────────────────────────────────────

def test_grade_chips_are_derived_not_hardcoded():
    """写死的后果是两头出错：A+ 是幽灵按钮（生产 247 只里一只都没有），
    C+（14 只）和 NR 根本筛不出来。"""
    tpl = _read('templates/watchlist.html')
    assert "['A+','A','B+','B','B-','C','D']" not in tpl
    assert "for g in wl_grades" in tpl


def test_grade_filter_not_gated_on_having_multiple_markets():
    """只持有 A股 的用户（妈妈就是）以前完全看不到等级按钮 ——
    等级筛选跟「有没有多个市场」毫无关系，是被市场筛选连坐了。"""
    tpl = _read('templates/watchlist.html')
    block = tpl[tpl.index('id="wl-filter-bar"') - 400:tpl.index('wl-filter-clear')]
    assert 'wl_grades | length > 1' in block


def test_service_exposes_wl_grades():
    src = _read('radar_app/watchlist/service.py')
    assert '"wl_grades": wl_grades' in src


# ── 排序 ────────────────────────────────────────────────

def test_missing_change_pct_is_empty_not_zero():
    """`{{ s.change_pct or 0 }}` 把拿不到价的股票写成 0%，排序时夹在
    真实的 +2% 和 -3% 中间，看起来像「今天没动」。"""
    tpl = _read('templates/watchlist.html')
    assert 'data-change="{{ s.change_pct or 0 }}"' not in tpl
    assert "s.change_pct if s.change_pct is not none" in tpl


def test_change_sort_sinks_missing_values():
    tpl = _read('templates/watchlist.html')
    seg = tpl[tpl.index("if (by === 'change')"):][:600]
    assert 'na !== nb' in seg and 'na ? 1 : -1' in seg


# ── 筛选与搜索必须能叠加 ────────────────────────────────

def test_filter_and_search_share_one_visibility_path():
    """两者原本各自直接写 el.style.display，谁后跑谁覆盖谁：
    先按 A 级筛、再搜个名字，筛选就没了；反过来也一样。"""
    tpl = _read('templates/watchlist.html')
    assert 'function applyVisibility()' in tpl
    # 搜索函数里不许再直接改 display
    seg = tpl[tpl.index('function filterBySearch'):]
    seg = seg[:seg.index('function clearSearch')]
    assert 'style.display' not in seg.replace("clear.style.display", "")


def test_clearing_filters_keeps_the_search():
    tpl = _read('templates/watchlist.html')
    seg = tpl[tpl.index('function clearWlFilters'):][:500]
    assert 'applyVisibility()' in seg
    assert "forEach(el => el.style.display = '')" not in seg


# ── 端到端 ──────────────────────────────────────────────

def test_filter_endpoint_end_to_end():
    import db
    db.init_db()
    from app import app
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 1
    for q in ('grade=A', 'grade=C%2B', 'grade=NR', 'market=cn'):
        r = c.get('/api/watchlist/filter?' + q)
        assert r.status_code == 200, f"{q} → {r.status_code}"
        assert 'codes' in r.get_json()
