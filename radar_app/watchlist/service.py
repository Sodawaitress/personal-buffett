"""Watchlist service orchestration."""

from datetime import datetime

import db
from radar_app.legacy.pipeline import classify_stock_code, start_pipeline_job
from radar_app.shared.market import detect_market
from radar_app.shared.runtime import CN_TZ
from radar_app.watchlist.presenter import calc_judgment_growth, calc_performance_stats, present_performance_row, present_watchlist_stock
from radar_app.data.analysis import get_leaderboard
from radar_app.data.stocks import get_news_sentiment_map, get_upcoming_events_for_user
from radar_app.watchlist.query import (
    get_active_notifications,
    get_performance_rows,
    get_quote_map,
    get_watchlist_snapshot,
    list_watchlist_rows,
)


def _portfolio_volatility(codes):
    """US-209：整个自选股一起颠多少。

    ⚠️ **不能把个股波动平均。** 五只都颠 4 倍的股票凑一起，组合不一定颠 4 倍
    —— 它们不同涨同跌的那部分会互相抵消。必须先合成**组合的周收益序列**
    再算标准差，相关性才会被正确算进去。

    实测（2026-09-07 生产数据）：
        全高波动组合   实际 2.6 倍，直接平均会得到 3.5 倍
        混合组合       实际 1.0 倍，直接平均会得到 1.6 倍
    混合组的分散收益反而更大（38% vs 26%）—— 因为银行电力和 AI 股不同涨同跌。

    没有持仓量（`user_watchlist` 只有 buy_price），所以按**等权重**，
    并在页面上写明。
    """
    import json as _json
    if not codes:
        return None
    try:
        from sqlalchemy import text
        from radar_app.data.core import get_engine
        from scripts.volatility_profile import (BENCHMARK, describe_portfolio,
                                                portfolio_profile)
        with get_engine().begin() as conn:
            rows = conn.execute(text(
                "SELECT code, vol_series FROM stock_fundamentals "
                "WHERE vol_series IS NOT NULL"), ).mappings().all()
        want = set(codes)
        series = []
        for r in rows:
            if r["code"] not in want:
                continue
            try:
                v = _json.loads(r["vol_series"] or "[]")
            except Exception:
                v = []
            if v:
                series.append(v)
        if len(series) < 3:          # 太少了谈不上组合
            return None
        bench = _bench_returns("cn")
        if not bench:
            return None
        p = portfolio_profile(series, bench, market="cn")
        return {**p, **describe_portfolio(p)} if p else None
    except Exception:
        return None


_BENCH_CACHE = {}


def _bench_returns(market):
    """基准的周收益。缓存住 —— 每次开自选股页都去拉 500 天日线太慢。"""
    import time
    hit = _BENCH_CACHE.get(market)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    try:
        import akshare as ak
        from scripts.volatility_profile import BENCHMARK, weekly_returns
        cl = list(ak.stock_zh_index_daily(
            symbol=BENCHMARK[market][0])["close"].astype(float))[-500:]
        rs = weekly_returns(cl)
        _BENCH_CACHE[market] = (time.time(), rs)
        return rs
    except Exception:
        return hit[1] if hit else None


def build_watchlist_context(user_id):
    rows = list_watchlist_rows(user_id)
    codes = [row.get("stock_code") or row.get("code") for row in rows]
    sentiment_map = get_news_sentiment_map(codes)

    stocks = []
    for row in rows:
        code = row.get("stock_code") or row.get("code")
        market = row.get("market") or detect_market(code)
        stocks.append(present_watchlist_stock(row, get_watchlist_snapshot(code, market), sentiment_map.get(code)))

    # US-159：质量分排名并进每只股票。复用 get_leaderboard（与原擂台同一套
    # 计算），所以名次/升降/走势线在卡片和列表里就地可渲染，不再需要独立视图 ——
    # 也因此筛选自动生效（就是同一个列表），不会再出现「筛了 A股 却排出港美股」。
    try:
        board = {b["code"]: b for b in (get_leaderboard(user_id) or [])}
    except Exception:
        board = {}
    for s in stocks:
        b = board.get(s["code"]) or {}
        s["rank"] = b.get("rank")
        s["score_change"] = b.get("score_change")
        s["rank_change"] = b.get("rank_change")
        s["spark"] = b.get("spark") or []

    # 榜单上最新的分析日期：比它旧的股票要标出来，否则等于拿不同日子的分排名次
    dates = [s.get("analysis_date") for s in stocks if s.get("analysis_date")]
    freshest = max(dates) if dates else ""

    # 差评（D/D-）沉底，稳定排序保留"新在前"（US-125）
    stocks.sort(key=lambda s: s.get("is_poor", False))

    markets = sorted({s["market"] for s in stocks if s.get("market")})

    # US-168：等级按钮由**用户自己实际持有的等级**生成，不再写死一串。
    # 写死的后果是两头出错：A+ 是幽灵按钮（生产 247 只里一只都没有），
    # 而 C+（14 只）和 NR（没分析过的）根本筛不出来。
    # 跟 wl_markets 同一个模式 —— 按钮只会出现在筛得出东西的时候。
    from radar_app.watchlist.presenter import GRADE_UNRATED, grade_rank
    grades = {(s.get("grade") or "").strip().upper() or GRADE_UNRATED
              for s in stocks}
    wl_grades = sorted(grades - {"—"},
                       key=lambda g: (grade_rank(g), g))
    return {
        "stocks": stocks,
        "portfolio_vol": _portfolio_volatility(codes),
        "holding": [s for s in stocks if s["status"] == "holding"],
        "watching": [s for s in stocks if s["status"] == "watching"],
        "sold":    [s for s in stocks if s["status"] == "sold"],
        "has_cn_stocks": any(s.get("market") == "cn" for s in stocks),
        "freshest_analysis_date": freshest,
        "wl_markets": markets,
        "wl_grades": wl_grades,
        "notifications": get_active_notifications(user_id),
        "upcoming_events": get_upcoming_events_for_user(user_id, days_ahead=7),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "now_date": datetime.now(CN_TZ).strftime("%Y-%m-%d"),
    }


def add_stock_and_start_analysis(user_id, code, name, market, notes, asset_type=None):
    if not market:
        market = detect_market(code)
    if market == 'nz' and not code.endswith('.NZ'):
        code += '.NZ'

    db.add_user_stock(user_id, code, name, market, notes=notes, asset_type=asset_type)

    try:
        classify_stock_code(code)
    except Exception:
        pass

    start_pipeline_job(user_id, code, market)
    return code, market


def update_watchlist_stock_status(user_id, code, data):
    status = data.get('status')
    if status not in ('watching', 'holding', 'sold'):
        return None

    entry_grade = None
    if status == 'holding':
        analysis = db.get_latest_analysis(code, period='daily')
        if analysis:
            entry_grade = analysis.get('grade')

    db.update_stock_status(
        user_id,
        code,
        status,
        buy_date=data.get('buy_date'),
        buy_price=float(data['buy_price']) if data.get('buy_price') else None,
        sell_date=data.get('sell_date'),
        sell_price=float(data['sell_price']) if data.get('sell_price') else None,
        entry_grade=entry_grade,
    )
    return {'ok': True, 'entry_grade': entry_grade}


def build_performance_context(user_id):
    quote_map = get_quote_map()
    today = datetime.now(CN_TZ).date()

    holdings = []
    sold = []
    for row in get_performance_rows(user_id):
        perf = present_performance_row(row, quote_map.get(row["code"], {}), today)
        if row["status"] == "holding":
            holdings.append(perf)
        else:
            sold.append(perf)

    all_rows = holdings + sold
    return {
        "holdings":        holdings,
        "sold":            sold,
        "stats":           calc_performance_stats(all_rows),
        "judgment_growth": calc_judgment_growth(all_rows),
        "now":             datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }
