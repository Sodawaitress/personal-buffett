"""还原真实盈利：把一次性收益从净利润里剔掉，再算市盈率。

## 为什么要有这个

2026-08-25，用户问「多邻国值不值得买」。我们网站显示 **市盈率 13.28 倍** ——
看起来便宜得不像话。而市场给的前瞻市盈率是 48–53 倍。差了近 4 倍。

原因在 `pipeline_fetch.py`：

    "pe_current": info.get("trailingPE")    # 直接抄数据源的滚动市盈率

一次性收益原样吞了进来。DUOL 2025 年报（yfinance / SEC 10-Q 均可验证）：

    税前利润    $182.4M
    所得税      −$231.7M    ← 负数。不是交税，是退税
    净利润      $414.1M     ← **净利润 > 税前利润**

来源是「递延所得税估值备抵释放」：公司长期亏损时计提的税务资产，
在确认将来能持续盈利的那一年一次性转回。**这是会计事件，不是生意变好。**
DUOL 在 10-Q 里明确披露全年一次性税收收益 **$256.7M**。

    账面净利 414.1 − 一次性 256.7 = 真实 157.4
    市值 6870 ÷ 414.1 = 16.6 倍   ← 网站显示的
    市值 6870 ÷ 157.4 = 43.7 倍   ← 真实的，和前瞻 48–53 对得上

## 判据

**美股（有税前利润）：净利润 > 税前利润 ⇒ 必有一次性税收收益。**
这条是硬的 —— 正常情况下 净利润 = 税前利润 − 所得税，税是正数，
所以净利润必然小于税前利润。反过来只能是税项为负。

还原方法：用公司**自己历史上的有效税率**（而不是法定税率）反推：

    还原净利润 = 税前利润 × (1 − 历史有效税率)

DUOL 用 2024 年的 13.4% 算：182.4 × 0.866 = **158.0M**
和 10-Q 披露值倒推的 157.4M 相差 0.4% —— **两条独立路径互相验证**。

**A股（没有税前利润字段，但有经营现金流）**：退而求其次，看
净利润与经营现金流的背离。一次性收益不产生经营现金流，所以
「净利润暴涨、现金流没跟上」是同一件事的影子。这条是**提示**，
不是判定 —— 现金流背离也可能是应收账款、存货造成的。

## 不做什么

- **不替用户判断「贵还是便宜」**：只把真实的分母摆出来。43.7 倍是贵是便宜，
  取决于增速和护城河，那是另一层判断。
- **不追溯改写历史数据**：只在展示时标注，原始值保留。数据源怎么给的
  就怎么存，是本仓一贯做法（改写原始值会让以后对不上账）。
"""

# 没有历史有效税率可参考时的兜底（美国联邦法定 21%，A股 25%）
_DEFAULT_RATE = {"us": 0.21, "cn": 0.25, "hk": 0.165, "nz": 0.28, "au": 0.30}
_FALLBACK_RATE = 0.21

# 有效税率取值区间：超出这个范围的年份不拿来当「正常年份」
_MIN_RATE, _MAX_RATE = 0.05, 0.40


# A 股的年报字段是带单位的字符串（'823.20亿'、'1,720.54亿'、'5300万'），
# 美股的是裸浮点。US-202：`float('823.20亿')` 抛异常 → 返回 None
# → `has_tax_windfall` 当成缺数据 → **A 股的一次性收益检测静默失效**。
#
# 这是「拿一个语境的事实用到另一个语境」的第三次（US-154/168/171 数据库，
# US-198 内部人披露规则）。这次的形态最隐蔽：它不报错，只是永远返回 False。
_UNIT = {"亿": 1e8, "万": 1e4, "千": 1e3}


def _num(v):
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace("，", "")
        if not t:
            return None
        mult = 1.0
        for u, m in _UNIT.items():
            if t.endswith(u):
                t, mult = t[:-len(u)], m
                break
        try:
            f = float(t) * mult
        except ValueError:
            return None
        return f if f == f else None
    try:
        f = float(v)
        return f if f == f else None      # 挡掉 NaN
    except (TypeError, ValueError):
        return None


def has_tax_windfall(row: dict) -> bool:
    """净利润 > 税前利润 ⇒ 税项为负 ⇒ 有一次性税收收益。

    这是**结构性**判据，不是阈值猜测：正常情况下税是支出，
    净利润必然小于税前利润。
    """
    pre = _num(row.get("pretax_income"))
    net = _num(row.get("net_profit"))
    if pre is None or net is None or pre <= 0:
        return False
    return net > pre


def effective_tax_rate(row: dict):
    """单年的有效税率。税项为负（退税年）返回 None —— 那年不能当基准。"""
    pre = _num(row.get("pretax_income"))
    tax = _num(row.get("tax_provision"))
    if pre is None or tax is None or pre <= 0 or tax < 0:
        return None
    r = tax / pre
    return r if _MIN_RATE <= r <= _MAX_RATE else None


def _normal_rate(annual: list, market: str = "us"):
    """公司自己历史上的有效税率中位数；没有可用年份就退回法定税率。

    用公司自己的比法定的准 —— 软件公司普遍有研发抵扣，
    实际税率长期低于法定。
    """
    rates = [r for r in (effective_tax_rate(y) for y in annual or []) if r is not None]
    if not rates:
        return _DEFAULT_RATE.get(market, _FALLBACK_RATE), "法定税率"
    rates.sort()
    mid = rates[len(rates) // 2] if len(rates) % 2 else \
        (rates[len(rates) // 2 - 1] + rates[len(rates) // 2]) / 2
    return mid, "公司历史有效税率"


def normalize(annual: list, market: str = "us") -> dict:
    """还原最近一个财年的真实净利润。

    返回 {} 表示无需还原或数据不足 —— **绝不猜**。
    有结果时返回:
      {year, reported, normalized, one_off, rate, rate_source, ratio, reason}
    金额单位与输入一致（本仓年报里是「亿」）。
    """
    if not annual:
        return {}
    latest = annual[0] or {}
    if not has_tax_windfall(latest):
        return {}

    pre = _num(latest.get("pretax_income"))
    net = _num(latest.get("net_profit"))
    rate, src = _normal_rate(annual[1:], market)      # 用**往年**的税率，不含出事这年
    norm = round(pre * (1 - rate), 4)
    if norm <= 0:
        return {}
    return {
        "year":        latest.get("year"),
        "reported":    net,
        "normalized":  norm,
        "one_off":     round(net - norm, 4),
        "rate":        round(rate, 4),
        "rate_source": src,
        "ratio":       round(net / norm, 2),
        "reason":      "一次性所得税收益（递延所得税估值备抵释放等）",
    }


def adjusted_pe(reported_pe, norm: dict):
    """把账面市盈率按「真实净利润」还原。

    账面 PE = 市值 / 账面净利，还原 PE = 市值 / 真实净利，
    所以 还原PE = 账面PE × (账面净利 / 真实净利)。
    不需要知道市值 —— 比值就够了。
    """
    pe = _num(reported_pe)
    if pe is None or pe <= 0 or not norm:
        return None
    ratio = norm.get("ratio")
    if not ratio or ratio <= 0:
        return None
    return round(pe * ratio, 1)


def cashflow_divergence(row: dict, prev: dict = None) -> dict:
    """A股兜底：净利润与经营现金流背离。

    一次性收益不产生经营现金流。但现金流背离也可能是应收/存货造成的，
    所以这条只是**提示**，措辞必须留有余地，不能说成「有一次性收益」。
    """
    net = _num(row.get("net_profit"))
    cfo = _num(row.get("cfo"))
    if net is None or cfo is None or net <= 0:
        return {}
    ratio = cfo / net
    if ratio >= 0.5:
        return {}
    return {"ratio": round(ratio, 2),
            "hint": f"经营现金流只有净利润的 {ratio:.0%}，利润质量存疑"}


def describe(norm: dict, reported_pe=None, locale: str = "zh") -> str:
    """一句人话。给妈妈看的，不能出现「递延所得税估值备抵」这种词。"""
    if not norm:
        return ""
    adj = adjusted_pe(reported_pe, norm)
    if locale == "en":
        s = (f"{norm['year']} profit includes a one-off tax gain. "
             f"Excluding it, real profit is about {norm['normalized']} "
             f"(reported {norm['reported']}).")
        if adj:
            s += f" Real P/E is about {adj}x, not {round(float(reported_pe), 1)}x."
        return s
    s = (f"{norm['year']} 年的利润里有一笔**一次性的退税**，不是生意赚来的。"
         f"扣掉之后真实利润约 {norm['normalized']}（账面 {norm['reported']}）。")
    if adj:
        s += f"\n所以真实市盈率约 **{adj} 倍**，不是账面上的 {round(float(reported_pe), 1)} 倍。"
    return s
