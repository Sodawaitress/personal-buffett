"""US-208：颠不颠 —— 以及「不知道」不许被讲成「知道」。

起因是用户妈妈：8 月赚了钱，9 月「又被吃进去了」，她以为是「突然战争了」。
实际是中证1000 八月 +9.8%、8/19 单日 -5.4% —— **赚的和赔的来自同一批股票**。

国内软件只有「振幅」（当日最高最低之差），回答「今天活跃吗」，
不回答「平时颠成什么样、比大盘颠多少」。
"""
import math

import pytest

from scripts.volatility_profile import (_peer_phrase, describe, is_stable,
                                        profile, volatility, weekly_returns)


def _walk(n, step, seed=1.0):
    """确定性的锯齿序列：每周固定振幅 step，用来造已知波动率的数据。"""
    out, v, up = [seed], seed, True
    for i in range(n):
        v = v * (1 + step) if up else v * (1 - step)
        if i % 5 == 4:
            up = not up
        out.append(v)
    return out


def test_volatility_needs_enough_history():
    assert volatility([1.0] * 50) is None, "数据不够却给了结论"
    assert volatility(_walk(400, 0.01)) is not None


def test_ratio_separates_calm_from_choppy():
    calm, wild = _walk(400, 0.002), _walk(400, 0.02)
    p_calm = profile(calm, calm, "cn")
    p_wild = profile(wild, calm, "cn")
    assert p_wild["ratio"] > p_calm["ratio"] * 3


def test_unknown_stability_is_not_reported_as_changed():
    """US-208 第一版写成 `if p.get("stable") else`，
    于是 None（数据不够，判不了）被当成 False —— 实测四只股票**全部**
    报「脾气最近变了」，一个从不说「稳定」的稳定性判断。

    又是把「不知道」讲成「知道」（US-202 全篇同一族）。
    """
    short = _walk(200, 0.01)            # 只够算波动，不够判稳定性
    assert is_stable(short) is None
    d = describe(profile(short, short, "cn"))
    assert "判断不了" in d["stable"], d["stable"]
    assert "变了" not in d["stable"]


def test_stability_says_stable_when_it_is():
    steady = _walk(600, 0.01)
    assert is_stable(steady) is True
    d = describe(profile(steady, steady, "cn"))
    assert "一直是这个脾气" in d["stable"]


def test_meaning_comes_before_numbers():
    """人话原则：先说对她意味着什么，再说数字。
    `meaning` 里必须是「涨跌 1 块 / 涨跌 N 块」这种能想象的东西，
    不能只有「周波动率 10.4%」。"""
    d = describe(profile(_walk(400, 0.02), _walk(400, 0.002), "cn"))
    assert "块" in d["meaning"], d["meaning"]
    assert "%" not in d["headline"], "标题里塞了百分比，读的人得先换算"


@pytest.mark.parametrize("pct,expect", [
    (100, "比 99% 的股票更颠"),      # 不许说 100%，那像口号不像事实
    (80,  "比 80% 的股票更颠"),
    (20,  "比 80% 的股票更稳"),      # 最稳的那只该说「更稳」，别让人脑内反算
    (0,   "比 99% 的股票更稳"),
])
def test_peer_phrase_reads_the_way_people_think(pct, expect):
    assert _peer_phrase(pct, "zh") == expect


def test_benchmark_is_same_market():
    """拿沪深300 去比美股，倍数没有意义 —— US-202 那一整族错误。"""
    from scripts.volatility_profile import BENCHMARK
    for m in ("cn", "us", "hk", "nz"):
        assert m in BENCHMARK


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_no_language_mixing(locale):
    d = describe(profile(_walk(600, 0.02), _walk(600, 0.002), "cn"), locale)
    for v in d.values():
        if not v:
            continue
        has_cn = any("一" <= c <= "鿿" for c in v)
        assert has_cn == (locale != "en"), (locale, v)


def _extract_block(path, var):
    """按 `{% if %}`/`{% endif %}` **配对计数**取出一段模板。

    这个仓里我已经切坏过四次模板了 —— 每次都是按注释文字或第一个
    `{% endif %}` 去切，结果切在 `{# ... #}` 中间或嵌套块中间，
    得到一段语法不完整的模板，测试报 TemplateSyntaxError，
    看着像模板坏了，其实是**测试的取法坏了**。

    配对计数一次写对，以后所有卡片的渲染测试都能用。
    """
    import re
    src = open(path, encoding="utf-8").read()
    start = src.index("{%% if %s %%}" % var)
    depth, i = 0, start
    for m in re.finditer(r"{%-?\s*(if|endif)\b", src[start:]):
        depth += 1 if m.group(1) == "if" else -1
        if depth == 0:
            i = start + m.end()
            break
    return src[start:src.index("%}", i) + 2]


def test_card_renders_with_real_shaped_data():
    """守渲染：卡片不能因为缺字段就崩，也不能显示「—」占位。

    第一版模板引了 `volatility.bench_vol`，但那个值没存进库 ——
    页面会安静地显示「—」，看起来像数据源坏了。
    它其实等于 vol / ratio，反推即可，不必为派生值多加一列。
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=select_autoescape(["html"]))
    seg = _extract_block("templates/stock/signals.html", "volatility")

    vol = {"vol": 10.4, "ratio": 3.9, "bench_vol": 2.7, "pct": 80,
           "bench_name": "沪深300", "stable": True,
           "headline": "比沪深300颠 3.9 倍",
           "meaning": "沪深300涨跌 1 块，它通常涨跌 3.9 块 —— 涨的时候特别爽，跌的时候也特别快。",
           "stable_text": "", "peers": "比 80% 的股票更颠"}
    vol["stable"] = "这一年它一直是这个脾气，接下来大概率还这样。"
    html = env.from_string(seg).render(volatility=vol)

    assert "比沪深300颠 3.9 倍" in html
    assert "涨跌 3.9 块" in html
    assert "—%" not in html and "— %" not in html, "基准波动显示成了占位符"
    assert "2.7%" in html, "基准波动没渲染出来"
    # 「不预测方向」这句必须在，它是这个卡片的边界
    assert "不预测涨跌方向" in html


def test_presenter_derives_bench_vol():
    import inspect
    from radar_app.stocks import presenter
    src = inspect.getsource(presenter)
    assert '"bench_vol"' in src, "presenter 没有算基准波动，页面会显示占位符"


# ── 组合层（US-209）────────────────────────────────────────────────────────

def test_portfolio_vol_is_not_the_average_of_members():
    """**最容易写错的一条。**

    五只都颠 4 倍的股票凑一起，组合不一定颠 4 倍 —— 不同涨同跌的部分会抵消。
    直接平均个股波动会**系统性高估**。

    实测（生产数据 2026-09-07）：
        全高波动组合   实际 2.6 倍   直接平均 3.5 倍
        混合组合       实际 1.0 倍   直接平均 1.6 倍
    """
    import random
    from scripts.volatility_profile import portfolio_profile
    rnd = random.Random(42)
    bench = [rnd.gauss(0, 0.02) for _ in range(120)]
    # 五条**互不相关**的高波动序列
    members = [[rnd.gauss(0, 0.08) for _ in range(120)] for _ in range(5)]
    p = portfolio_profile(members, bench, market="cn")
    assert p, "算不出组合波动"
    assert p["ratio"] < p["naive_ratio"], (
        f"组合波动 {p['ratio']} 没有低于平均 {p['naive_ratio']} —— 相关性没算进去")
    assert p["diversification"] > 30, "五条独立序列的分散收益应该很明显"


def test_perfectly_correlated_members_get_no_diversification():
    """反向边界：成员完全同涨同跌 → 分散收益接近 0。
    如果这里也报出一个漂亮的折扣，说明算法在凭空造分散。"""
    import random
    from scripts.volatility_profile import portfolio_profile
    rnd = random.Random(7)
    one = [rnd.gauss(0, 0.06) for _ in range(120)]
    bench = [rnd.gauss(0, 0.02) for _ in range(120)]
    p = portfolio_profile([one[:], one[:], one[:]], bench, market="cn")
    assert p and abs(p["diversification"]) <= 3, (
        f"完全相关却报出 {p['diversification']}% 的分散收益")


def test_portfolio_needs_enough_members_and_history():
    from scripts.volatility_profile import portfolio_profile
    assert portfolio_profile([], [0.01] * 60) == {}
    assert portfolio_profile([[0.01] * 10], [0.01] * 60) == {}


def test_watchlist_row_renders_and_shows_the_wrong_answer_too():
    """页面要同时显示「直接平均会得到几倍」—— 不是为了炫技，
    是为了让人知道分散省下了多少，而不是以为组合本来就该这么稳。"""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=select_autoescape(["html"]))
    seg = _extract_block("templates/watchlist.html", "portfolio_vol")
    pv = {"ratio": 2.6, "naive_ratio": 3.5, "diversification": 26, "n": 5,
          "bench_name": "沪深300", "vol": 7.0, "bench_vol": 2.7,
          "headline": "你的自选股整体比沪深300颠 2.6 倍",
          "meaning": "沪深300涨跌 1 块，你这 5 只加起来通常涨跌 2.6 块。",
          "diversify": "分散在 5 只上，比只拿一只少颠了 26%。",
          "note": "按等权重算（自选股没有记持仓量）。"}
    html = env.from_string(seg).render(portfolio_vol=pv)
    assert "颠 2.6 倍" in html
    assert "3.5 倍" in html and "高估" in html, "没告诉人错误答案长什么样"
    assert "等权重" in html, "没说明权重假设"
