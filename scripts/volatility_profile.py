"""US-208：这只股票颠不颠 —— 以及「颠」能预测什么、不能预测什么。

**为什么要有这个**：用户妈妈 2026 年 8 月赚了钱，9 月「又被吃进去了」，
她以为是「突然战争了」。实际是：

    8月  中证1000 +9.8%   沪深300 +0.8%    ← 她赚的钱在小盘股
    8/19 创业板 -6.3%     沪深300 -2.9%    ← 跌得最狠的正是涨得最猛的

**她赚的钱和赔的钱来自同一批股票。** 不是运气，是同一个仓位的两个方向。

国内软件（同花顺/东财/雪球）只有「振幅」——当日最高最低之差，
回答「今天活跃吗」，**不回答「平时颠成什么样、比大盘颠多少」**。
所以她天天看行情，却从没被告知这件事。

## 能预测什么

**波动率聚集**（volatility clustering，金融学最稳的实证之一）：
价格变化本身几乎没有自相关（**方向不可预测**），
但变化的绝对值有很强的长期自相关 —— **大波动后面跟着大波动**。

    ❌ 「它昨天跌了，明天会涨吗」      → 没有信息
    ✅ 「它最近很颠，接下来还会颠吗」  → 会，而且相当可靠

所以这个模块的预测价值是**预期管理**，不是择时。

## 顺带一提的横截面规律（**不用于个股判断**）

中国 A 股的研究：低波动股票长期显著跑赢高波动股票，
而且驱动因素是**波动率而非贝塔**（这点和美国不同，别照搬 Beta）。
1994–2014 数据显示特异波动率与未来收益显著负相关。

**但这是「一组 vs 一组」的长期平均，推不出「这一只会跌」。**
所以模块只描述事实，不产出买卖信号。而且 A 股机构化在推进，
异象会衰减 —— 今天成立不代表五年后成立。

## 措辞参考

Simply Wall St 的 "Volatility Over Time"：

    "SPPL's weekly volatility (15%) has been stable over the past year,
     but is still higher than 75% of US stocks."

三段式：**绝对水平 / 这个颠法稳不稳定 / 和别人比**。
第二段是最聪明的地方 —— 它说的是「**波动水平**稳定」而不是「股价稳定」，
正好对应波动率聚集，没有越界去说方向。

本模块沿用这个三段式，但把「百分位」换成「**是大盘的几倍**」打头 ——
「高于 92% 的 A 股」没有体感，「**颠 2.8 倍**」有。
"""
from __future__ import annotations

import math

_MIN_WEEKS = 30          # 少于 30 个周收益 → 不给结论
_STABLE_BAND = 0.35      # 近半年波动 vs 前半年，差异在 ±35% 内算「稳定」

# 各市场的对照基准。**必须和股票同市场** —— 拿沪深300 去比美股，
# 得到的倍数没有意义（US-202 那一整族错误：跨语境套用）。
BENCHMARK = {
    "cn": ("sh000300", "沪深300"),
    "us": ("^GSPC", "标普500"),
    "hk": ("^HSI", "恒生指数"),
    "nz": ("^NZ50", "新西兰50"),
}


def weekly_returns(closes: list) -> list:
    """日收盘 → 周收益。取每 5 个交易日一段，避开节假日对齐问题。"""
    out = []
    for i in range(5, len(closes), 5):
        a, b = closes[i - 5], closes[i]
        if a and b and a > 0:
            out.append(b / a - 1)
    return out


def _std(xs: list):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def volatility(closes: list):
    """周波动率（标准差，百分数）。数据不够就返回 None，不猜。"""
    rs = weekly_returns(closes)
    if len(rs) < _MIN_WEEKS:
        return None
    s = _std(rs)
    return round(s * 100, 1) if s is not None else None


def is_stable(closes: list):
    """**波动水平**稳不稳定 —— 不是股价稳不稳定，两回事。

    比较后半段和前半段的波动率。差异在 ±35% 内 → 稳定，
    意思是「这个颠法会延续」（波动率聚集）。
    差异大 → 它的性格最近变了，历史倍数的参考价值下降。
    """
    rs = weekly_returns(closes)
    if len(rs) < _MIN_WEEKS * 2:
        return None
    half = len(rs) // 2
    old, new = _std(rs[:half]), _std(rs[half:])
    if not old or not new:
        return None
    return abs(new / old - 1) <= _STABLE_BAND


def profile(closes: list, bench_closes: list, market: str = "cn",
            peer_vols: list = None) -> dict:
    """返回 {} 或 {vol, bench_vol, ratio, stable, pct, bench_name}。"""
    v = volatility(closes)
    bv = volatility(bench_closes)
    if v is None or not bv:
        return {}
    out = {
        "vol": v,
        "bench_vol": bv,
        "bench_name": BENCHMARK.get(market, ("", "大盘"))[1],
        "ratio": round(v / bv, 1),
        "stable": is_stable(closes),
    }
    if peer_vols:
        below = sum(1 for p in peer_vols if p is not None and p <= v)
        out["pct"] = round(below / len(peer_vols) * 100)
    return out


def _peer_phrase(pct, locale):
    if pct is None:
        return None
    pct = max(1, min(99, pct))
    if locale == "en":
        return (f"choppier than {pct}% of stocks" if pct >= 50
                else f"calmer than {100 - pct}% of stocks")
    return (f"比 {pct}% 的股票更颠" if pct >= 50
            else f"比 {100 - pct}% 的股票更稳")


def describe(p: dict, locale: str = "zh") -> dict:
    """人话。**先说对她意味着什么，再说数字** —— 反过来她读不进去。

    组件语气跟仓里现有的走（「信息传到哪了」「有动静」那种），
    不引入新的说法。
    """
    if not p:
        return {}
    r, bn = p["ratio"], p["bench_name"]
    if locale == "en":
        word = "much choppier" if r >= 2 else ("choppier" if r >= 1.3
                else ("about the same" if r >= 0.8 else "calmer"))
        return {"peers": _peer_phrase(p.get("pct"), "en"),
                "headline": f"{word} than the market ({r}x)",
                "meaning": f"When the market moves 1, this typically moves {r}.",
                "stable": ("It has behaved this way all year."
                           if p.get("stable") is True else
                           ("Its temperament changed recently — the ratio is less reliable."
                            if p.get("stable") is False else
                            "Not enough history to judge whether that holds."))}

    if r >= 2:
        head, feel = f"比{bn}颠 {r} 倍", "涨的时候特别爽，跌的时候也特别快"
    elif r >= 1.3:
        head, feel = f"比{bn}颠一些（{r} 倍）", "起伏比大盘大"
    elif r >= 0.8:
        head, feel = f"和{bn}差不多（{r} 倍）", "跟着大盘走"
    else:
        head, feel = f"比{bn}稳（{r} 倍）", "涨得慢，跌得也慢"

    return {
        "headline": head,
        "meaning": f"{bn}涨跌 1 块，它通常涨跌 {r} 块 —— {feel}。",
        # ⚠️ 三态，不是两态。US-208 第一版写成 `if p.get("stable") else`，
        # 于是 None（数据不够，判不了）被当成 False，
        # 四只股票**全部**报「脾气最近变了」—— 一个从不说「稳定」的稳定性判断。
        # 又是把「不知道」讲成「知道」（US-202 全篇同一族）。
        "stable": ("这一年它一直是这个脾气，接下来大概率还这样。"
                   if p.get("stable") is True else
                   ("它的脾气最近变了，上面这个倍数参考价值下降。"
                    if p.get("stable") is False else
                    "历史不够长，判断不了这个脾气稳不稳定。")),
        # 人话：说「比 20% 的股票更颠」是对的，但读的人要在脑子里反过来算一次。
        # 最稳的那只就该说「更稳」。另外分位封在 1–99，
        # 「比 100% 的股票更颠」听起来像口号，不像事实。
        "peers": _peer_phrase(p.get("pct"), "zh"),
    }
