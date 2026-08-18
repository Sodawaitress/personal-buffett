"""US-159：擂台从「第三个视图」降级为「一种排序」。

原设计的四个问题（都在生产截图里能看到）：
  ① 藏得深：_viewCycle 是 card→list→arena 三态循环，要点两次才到，
     按钮文字还随之变化，无法预判
  ② 不跟筛选：loadArena() 直接 fetch('/api/leaderboard') 不带参数 ——
     用户筛了「A股」，擂台照样排出 MIXUE/Arista/Duolingo 等港美股
  ③ 看不到新鲜度：get_leaderboard 的 SQL SELECT 了 analysis_date 却没返回，
     而轮转是 2 天一圈 —— 等于拿「昨天算的分」和「前天算的分」排名次
  ④ 切走再回来不刷新：_arenaLoaded 一次性标志

改法：名次成为卡片/列表的装饰，「质量分」成为第 6 个排序选项。
筛选自动生效（就是同一个 DOM），新鲜度自动可见（两个视图本就显示日期）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _sort_by_score(items):
    """复刻 sortCards 的 score 分支：分数降序，无分(-1)沉底，同分按名次。"""
    return sorted(items, key=lambda x: (-x.get("score", -1), x.get("rank", 9999)))


def test_score_sort_descending():
    out = _sort_by_score([{"code": "A", "score": 82, "rank": 6},
                          {"code": "B", "score": 96, "rank": 1},
                          {"code": "C", "score": 88, "rank": 3}])
    assert [x["code"] for x in out] == ["B", "C", "A"]


def test_unscored_sinks_to_bottom():
    """没有 quant_score 的股票用 -1，必须沉底而不是排第一。"""
    out = _sort_by_score([{"code": "NR", "score": -1, "rank": 9999},
                          {"code": "A", "score": 60, "rank": 2}])
    assert [x["code"] for x in out] == ["A", "NR"]


def test_tie_broken_by_rank_stably():
    """同分（截图里 GUMING 和 POP MART 都是 82）必须有稳定次序。"""
    out = _sort_by_score([{"code": "POPMART", "score": 82, "rank": 6},
                          {"code": "GUMING", "score": 82, "rank": 5}])
    assert [x["code"] for x in out] == ["GUMING", "POPMART"]


# ── 新鲜度：跨股票比较必须看得见各自的分析日期 ──────────────

def _is_stale(stock_date, freshest):
    """复刻模板里的陈旧判定。"""
    return bool(stock_date and freshest and stock_date < freshest)


def test_older_analysis_flagged():
    """生产实测轮转 2 天一圈：同一榜单上必然同时存在两个日期。"""
    assert _is_stale("2026-08-17", "2026-08-18") is True


def test_newest_not_flagged():
    assert _is_stale("2026-08-18", "2026-08-18") is False


def test_missing_dates_not_flagged():
    """缺日期时不打标 —— 宁可不说，也不误报。"""
    assert _is_stale("", "2026-08-18") is False
    assert _is_stale("2026-08-17", "") is False


def test_leaderboard_returns_analysis_date():
    """回归：get_leaderboard 必须把 analysis_date 带出来。
    原来 SQL SELECT 了却没放进返回值，前端想显示也没有。"""
    import inspect

    from radar_app.data import analysis
    src = inspect.getsource(analysis.get_leaderboard)
    # 返回字典里必须出现 analysis_date
    assert '"analysis_date": x["analysis_date"]' in src


def test_arena_view_fully_removed():
    """擂台视图、loadArena、/api/leaderboard 路由都不该再存在。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    tpl = open(os.path.join(root, 'templates/watchlist.html')).read()
    assert 'wl-arena-view' not in tpl
    assert 'loadArena' not in tpl
    assert "data-sort=\"score\"" in tpl          # 取而代之的排序选项
    routes = open(os.path.join(root, 'radar_app/watchlist/routes.py')).read()
    assert "'/api/leaderboard'" not in routes


def test_view_cycle_has_no_arena():
    """视图循环只剩 card/list，不再有第三态。"""
    root = os.path.join(os.path.dirname(__file__), '..')
    tpl = open(os.path.join(root, 'templates/watchlist.html')).read()
    assert "['card', 'list']" in tpl
    assert "'arena'" not in tpl
