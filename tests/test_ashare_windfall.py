"""US-202 收尾：一次性收益检测在 A 股上一次都没生效过。

生产量出来的形态是**两个市场互为镜像**：

    美股 38 只：有税前利润 63%，有 PE 分位 **0%**
    A股 222 只：有 PE 分位 94%，有税前利润 **0%**

各缺对方有的那一半。补数脚本当初只写了美股那半边。

摊开之后是三层叠的，每一层都足以让检测静默失效：

1. **字段没存**。A 股的「利润总额」其实一直在抓（用来算 EBIT），
   只是没写进年报字段。
2. **字符串解析不了**。A 股字段是 '823.20亿' 这种带单位的串，
   `float()` 抛异常 → `_num` 返回 None → 当成缺数据 → 永远 False。
   它不报错，只是永远说「没有一次性收益」。
3. **单位不一致**。第一版我把税前存成「亿为单位的裸数字」1147.55，
   而同一行的 net_profit 是 '823.20亿' → 解析成 823 亿。
   两边差 1e8，**茅台会被判成有一次性收益**（实测确实会）。

第 2 条和 US-154/168/171（本地 SQLite vs 生产 Postgres）、
US-198（美股 Form 4 规则套到 A 股）同族：
**拿一个语境的事实用到另一个语境**。这次形态最隐蔽——不报错，只沉默。
"""
import pytest
from scripts.normalized_earnings import _num, has_tax_windfall, normalize

# 贵州茅台 2025 真实年报，**按仓库里的实际存储格式**（带单位的字符串）
MAOTAI_2025 = {"year": "2025", "revenue": "1720.54亿",
               "net_profit": "823.20亿", "pretax_income": "1147.55亿",
               "tax_provision": "294.45亿"}


@pytest.mark.parametrize("raw,expect", [
    ("823.20亿",   82320000000.0),
    ("1,720.54亿", 172054000000.0),   # 千分位逗号
    ("5300万",     53000000.0),
    ("1147.55",    1147.55),          # 美股裸数字
    (1147.55,      1147.55),
    ("", None), ("—", None), (None, None), ("abc", None),
])
def test_num_parses_both_markets_formats(raw, expect):
    assert _num(raw) == expect


def test_maotai_is_not_flagged_as_windfall():
    """单位不一致的回归守卫：茅台税前 1147.55亿 > 净利 823.20亿，
    完全正常。如果两个字段单位不同，它会被误判成有一次性收益。
    """
    assert has_tax_windfall(MAOTAI_2025) is False
    assert normalize([MAOTAI_2025], market="cn") == {}, "无需还原时必须返回空，不许猜"


def test_ashare_windfall_is_actually_detectable():
    """光有字段不够 —— 得证明检测**真的会响**。

    茅台返回 False 可能是算对了，也可能是解析失败默认 False。
    造一个真有一次性收益的 A 股样本，它必须为 True，
    否则前一条测试就是空转的绿。
    """
    fake = dict(MAOTAI_2025, net_profit="1500.00亿")   # 净利 > 税前
    assert has_tax_windfall(fake) is True


def test_fetcher_stores_pretax_in_the_same_unit_as_net_profit():
    """守的是**接线和单位**，不是算法：A 股 fetcher 里存税前利润的那行
    必须产出带「亿」的字符串，跟同一行的 net_profit 一致。
    """
    import inspect
    from scripts import stock_fetch_financials as f
    src = inspect.getsource(f.fetch_cn_advanced)
    assert '"pretax_income"' in src, "A 股没有存税前利润"
    assert '"tax_provision"' in src, "A 股没有存所得税"

    # 与其在源码里找「亿」（它出现在转换器定义里，位置不稳），
    # 不如**真的调用**那个转换器：单位对不对，让它自己说。
    ns = {}
    for line in src.splitlines():
        if "_yi_str" in line and "lambda" in line:
            exec(line.strip(), ns)
            break
    assert "_yi_str" in ns, "找不到 A 股金额转换器 _yi_str"
    out = ns["_yi_str"](114755000000.0)
    assert isinstance(out, str) and out.endswith("亿"), \
        f"税前利润没跟 net_profit 用同一个单位格式: {out!r}"
    assert _num(out) == pytest.approx(114755000000.0, rel=1e-4)


def test_statutory_rate_exists_for_every_market_we_hold():
    """税率表得覆盖 stocks.market 里真实出现的值（cn/us/hk/nz）。"""
    from scripts.normalized_earnings import _DEFAULT_RATE
    for m in ("cn", "us", "hk", "nz"):
        assert m in _DEFAULT_RATE, f"{m} 会退回美国税率 21%"
