"""US-203：给美股算市盈率历史分位 —— 以及承认什么时候算不出来。

**为什么需要这个**：US-202 量出两个市场是镜像的 ——

    美股 38 只：有当期 PE 63%，有 PE 分位 **0%**
    A股 222 只：有 PE 分位 94%，有税前利润 **0%**

A 股那半边（税前利润）已经补上了。这边补美股的分位。
没有分位，估值档只能靠股价位置，而股价位置说不了贵贱
（跌 80% 的股票如果利润跌 90%，反而更贵）——
于是 38 只美股全部落在「估值数据不足」。

**数据边界（实测，不是猜的）**：yfinance 的 `income_stmt` 对
AAPL / INTC / LULU / DUOL 一律只给 **4 期年度 EPS**，
`quarterly_income_stmt` 只给 5 期。所以：

- 能做：用「年度 EPS 阶梯」把 4 年的周线价格换算成 PE 序列，算分位
- **不能做**：真正的 5 年 TTM PE 曲线（缺季度历史）

所以这里报的是「**近 N 年**分位」，N 是实际覆盖到的年数，写进返回值里，
不许统一叫「5年分位」—— 那是把受限的观测讲成不受限的结论（US-202 全篇的主题）。

**两条硬规矩**：

1. **EPS ≤ 0 的年份整段剔除**。亏损年的 PE 是负数或无穷大，
   放进分位里会得到毫无意义的排名。
2. **正盈利覆盖不足 `_MIN_YEARS` 年就返回 None**，绝不硬凑。
   多邻国 2023 年才首次盈利，只有 2-3 年正利润，其中 2025 还被一次性
   退税扭曲 —— 对它来说「没有可比历史」是**正确答案**，不是缺陷。
"""
from __future__ import annotations

_MIN_YEARS = 3.0          # 少于 3 年正盈利覆盖 → 不给分位
_MIN_POINTS = 60          # 少于 60 个周线点 → 不给分位

# 「正利润」不等于「有意义的利润」。
#
# 生产首跑抓到的：AIA.NZ 区间 28–2315 倍（中位数 259），LITE 到 2623 倍。
# 那是公司微利那几年——EPS 接近 0，PE 就爆到几千倍。它是正数，
# 所以 `eps > 0` 放它过去了。
#
# 后果**有方向，而且是最危险的那个方向**：任何从微利恢复到正常盈利的
# 公司，历史区间都被那段天价 PE 占满，于是今天无论多贵都排在最低分位。
# 实测 NVDA 报第 0 百分位、FPH/HBM 报第 1 —— 全部看着「史上最便宜」。
#
# 这和 US-202 是同一个错误族：**把受限的观测讲成不受限的结论**。
# 「微利年的 PE」根本不是估值信息，不该参与排名。
_MAX_SANE_PE = 150.0
# 剔掉之后剩得太少 → 这家公司就是没有可比的估值历史，返回空
_MAX_DROPPED_RATIO = 0.25


def _annual_eps(ticker):
    """{fiscal_year_end(date) -> diluted EPS}，按时间升序。"""
    stmt = getattr(ticker, "income_stmt", None)
    if stmt is None or getattr(stmt, "empty", True):
        return []
    for key in ("Diluted EPS", "Basic EPS"):
        if key in stmt.index:
            ser = stmt.loc[key].dropna()
            return sorted(((c.date(), float(v)) for c, v in ser.items()),
                          key=lambda x: x[0])
    return []


def _eps_at(eps_points, day):
    """阶梯式 TTM EPS：取**已公布**的最近一个财年 EPS。

    财年结束当天就换成新 EPS 是不严谨的（真实公告要晚 1-2 个月），
    但误差只影响每年一小段，不改变分位的量级。这是这套数据能做到的上限，
    所以模块名和返回值都说「近 N 年分位」而不是精确 TTM。
    """
    val = None
    for d, e in eps_points:
        if d <= day:
            val = e
        else:
            break
    return val


def pe_percentile(ticker, normalized_eps_ratio=None):
    """返回 {pct, current, years, n, low, high, median} 或 {} —— 算不出就空。

    ⚠️ **排名用的是序列自己的最新 PE，不接受外部传入的 pe_current。**

    第一版接受 `current_pe`，生产上传的是库里的 `pe_current`（TTM 口径，
    最近四个季度）。而这条历史序列是**上一个完整财年的 EPS** 算的。
    两个口径不同：成长股 TTM 利润更高 → TTM 市盈率更低 → 拿去跟按年报算的
    历史比，永远排在低分位。

        NVDA  同口径第 28 → 混口径第 **0**
        SMCI  同口径第 55 → 混口径第 **5**
        AAPL  同口径第 99 → 混口径第 66

    偏差方向一致：**都让东西看起来更便宜**。和 US-202 全篇同一个错误族 ——
    拿一个语境的数字放进另一个语境的排名。

    所以这个参数被删掉了，不是改默认值。**能传错的接口，迟早会被传错。**

    normalized_eps_ratio：US-172 归一化后的「真实利润 / 账面利润」比。
    传进来时，历史 EPS 里被一次性收益抬高的那一年会被按比例还原，
    否则那年的 PE 会假性偏低，把整条分位往「贵」的方向拽。
    """
    eps_points = _annual_eps(ticker)
    if len(eps_points) < 2:
        return {}
    if normalized_eps_ratio and 0 < normalized_eps_ratio < 1:
        latest_day = eps_points[-1][0]
        eps_points = [(d, e * normalized_eps_ratio if d == latest_day else e)
                      for d, e in eps_points]

    try:
        hist = ticker.history(period="5y", interval="1wk")
    except Exception:
        return {}
    if hist is None or getattr(hist, "empty", True) or "Close" not in hist:
        return {}

    pes, covered_days, latest_pe, dropped = [], set(), None, 0
    for ts, close in hist["Close"].items():
        day = ts.date()
        eps = _eps_at(eps_points, day)
        if eps is None or eps <= 0 or close != close or close <= 0:
            continue                       # 亏损年 / 缺价 → 整点剔除
        pe = close / eps
        if pe > _MAX_SANE_PE:
            dropped += 1               # 微利年：不是「贵」，是「没有可比的利润」
            continue
        pes.append(pe)
        latest_pe = pe                     # ← 排序**之前**记下来
        covered_days.add(day)
    if len(pes) < _MIN_POINTS:
        return {}
    if dropped / (dropped + len(pes)) > _MAX_DROPPED_RATIO:
        return {}                          # 大半段历史没有有意义的利润

    years = (max(covered_days) - min(covered_days)).days / 365.25
    if years < _MIN_YEARS:
        return {}

    pes.sort()
    n = len(pes)
    # ⚠️ 不能写 `pes[-1]` —— 排完序它是**最大值**，于是每只股票都是第 100 百分位。
    # 第一版就是这么写的，AAPL 和 LULU 一起报 100，形态太整齐才看出来。
    cur = latest_pe
    below = sum(1 for p in pes if p <= cur)
    return {
        "pct": round(below / n * 100),
        "current": round(cur, 1),
        "basis": "上一完整财年 EPS",
        "years": round(years, 1),
        "n": n,
        "low": round(pes[0], 1),
        "high": round(pes[-1], 1),
        "median": round(pes[n // 2], 1),
    }


def describe(res: dict, locale: str = "zh") -> str:
    """把分位讲成人话，并且**把窗口写进句子里**。"""
    if not res:
        return ("正利润历史不足 3 年，没有可比的估值区间"
                if locale != "en" else
                "under 3 years of profitable history — no comparable valuation range")
    p, y, c = res["pct"], res["years"], res.get("current")
    if locale == "en":
        return (f"P/E {c}x — {p}th percentile of the past {y} years "
                f"(range {res['low']}–{res['high']}x, median {res['median']}x, "
                f"on last-full-year EPS)")
    return (f"市盈率 {c} 倍，处于近 {y} 年的第 {p} 百分位"
            f"（区间 {res['low']}–{res['high']} 倍，中位数 {res['median']} 倍；"
            f"按上一完整财年利润计）")
