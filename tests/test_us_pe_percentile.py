"""US-203：美股市盈率分位 —— 以及「算不出来」必须是个正当答案。

US-202 量出生产上 38 只美股一个分位都没有。补上之后，估值档才有真正的
估值证据可用（而不是拿股价位置冒充）。

两条最该守的：
1. **排序之后不能拿 `pes[-1]` 当当前值** —— 那是最大值，
   于是每只股票都报第 100 百分位。第一版就是这么写的，
   AAPL 和 LULU 一起报 100，形态太整齐才看出来。
2. **正利润历史不足就返回空**。多邻国 2023 年才首次盈利，
   INTC 刚扭亏 —— 对它们来说「没有可比历史」是正确答案。
"""
import datetime as dt

import pytest

from scripts.us_valuation_percentile import (_eps_at, describe, pe_percentile)


class _FakeStmt:
    """最小的 yfinance income_stmt 替身：只需要 .index / .loc / .empty。"""

    def __init__(self, mapping):
        self._m = mapping
        self.index = list(mapping.keys())
        self.empty = not mapping

    @property
    def loc(self):
        outer = self

        class _L:
            def __getitem__(self, k):
                class _S:
                    def __init__(self, d):
                        self._d = d

                    def dropna(self):
                        return self

                    def items(self):
                        return iter(self._d.items())
                return _S(outer._m[k])
        return _L()


class _FakeTicker:
    def __init__(self, eps_by_year, prices):
        self.income_stmt = _FakeStmt({"Diluted EPS": {
            _TS(dt.date(y, 12, 31)): v for y, v in eps_by_year.items()}})
        self._prices = prices

    def history(self, period=None, interval=None):
        return _FakeHist(self._prices)


class _FakeHist:
    """替身要长得像 DataFrame：真实代码会检查 `.empty` 和 `"Close" in hist`。
    少一个属性，被测函数就提前返回 {}，测试红得莫名其妙。"""

    def __init__(self, pairs):
        self._pairs = pairs
        self.empty = not pairs

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        return _Series(self._pairs)


class _TS:
    def __init__(self, d):
        self._d = d

    def date(self):
        return self._d


class _Series:
    def __init__(self, pairs):
        self._pairs = pairs
        self.empty = not pairs

    def items(self):
        return iter((_TS(d), p) for d, p in self._pairs)


def _weekly(start_year, years, price):
    out, d = [], dt.date(start_year, 1, 7)
    for _ in range(years * 52):
        out.append((d, price(d)))
        d += dt.timedelta(days=7)
    return out


def test_eps_step_uses_last_published_year():
    pts = [(dt.date(2023, 12, 31), 1.0), (dt.date(2024, 12, 31), 2.0)]
    assert _eps_at(pts, dt.date(2023, 6, 1)) is None      # 还没有任何年报
    assert _eps_at(pts, dt.date(2024, 6, 1)) == 1.0       # 用 2023 年的
    assert _eps_at(pts, dt.date(2025, 6, 1)) == 2.0


def test_current_pe_is_the_latest_not_the_max():
    """排序之后取 pes[-1] 会让所有股票都变成第 100 百分位。

    造一段价格：先高后低。当前 PE 应该落在**低分位**，
    如果实现取了排序后的最大值，就会报 100。
    """
    eps = {2021: 1.0, 2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0}
    prices = _weekly(2022, 4, lambda d: 200.0 if d.year <= 2024 else 20.0)
    res = pe_percentile(_FakeTicker(eps, prices))
    assert res, "应该算得出分位"
    assert res["pct"] < 50, f"当前价最低却报了第 {res['pct']} 百分位 —— 取成最大值了"


def test_loss_years_are_excluded_not_treated_as_cheap():
    """亏损年 PE 是负数。混进序列会排在最前面，把当前值推向高分位。"""
    # 正利润要覆盖 ≥3 年才会给分位，所以亏损年之后得留足时间
    eps = {2019: -2.0, 2020: -1.0, 2021: 1.0, 2022: 1.0, 2023: 1.0,
           2024: 1.0, 2025: 1.0}
    prices = _weekly(2020, 6, lambda d: 30.0)
    res = pe_percentile(_FakeTicker(eps, prices))
    assert res
    assert res["low"] > 0 and res["median"] > 0, "负 PE 漏进序列了"


def test_too_little_profitable_history_returns_empty():
    """多邻国/INTC 这类：只有 1-2 年正利润 → 不给分位，也不硬凑。"""
    eps = {2023: -1.0, 2024: -1.0, 2025: 1.0}
    prices = _weekly(2023, 3, lambda d: 50.0)
    assert pe_percentile(_FakeTicker(eps, prices)) == {}


def test_window_length_is_reported_not_assumed_to_be_five_years():
    """列名叫 pe_percentile_5y，但美股窗口实际 3.5-4 年。
    窗口长度必须出现在返回值和人话描述里 —— 否则又是一次
    「把受限的观测讲成不受限的结论」。
    """
    eps = {2021: 1.0, 2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0}
    prices = _weekly(2022, 4, lambda d: 100.0 + d.year)
    res = pe_percentile(_FakeTicker(eps, prices))
    assert "years" in res and res["years"] > 0
    assert f"{res['years']}" in describe(res), "人话里没写清楚是几年的窗口"
    assert "5年" not in describe(res) or res["years"] == 5.0


def test_windfall_year_is_normalized_before_ranking():
    """被一次性收益抬高的那年，EPS 虚高 → 那年 PE 假性偏低
    → 把整条历史分位往「贵」的方向拽。传入还原比例后必须变。
    """
    eps = {2021: 1.0, 2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 4.0}   # 2025 虚高
    # 价格必须延伸到 2025 年报生效**之后**，否则那年的 EPS 根本没被用上，
    # 还原比例自然看不出效果 —— 测试会红得像是代码坏了。
    prices = _weekly(2022, 5, lambda d: 100.0)
    plain = pe_percentile(_FakeTicker(eps, prices))
    fixed = pe_percentile(_FakeTicker(eps, prices), normalized_eps_ratio=0.25)
    assert plain and fixed
    # 虚高的 EPS 让那一年的 PE 假性偏低 → 它是区间的**下沿**（25 倍）。
    # 还原之后下沿被抬回真实水平（100 倍）。
    # 第一版我断言的是 high，方向反了 —— 一次性收益压低 PE，不是抬高。
    assert fixed["low"] > plain["low"], "还原比例没生效"
    assert fixed["pct"] > plain["pct"], "当前 PE 的分位应该被推高（不再显得便宜）"


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_describe_never_mixes_languages(locale):
    out = describe({}, locale)
    has_cn = any("一" <= c <= "鿿" for c in out)
    assert has_cn == (locale != "en"), out
