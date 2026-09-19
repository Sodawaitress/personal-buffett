"""US-216：这只股票有多少收入来自海外。

**起因**：用户妈妈说「有些评级 A 的票因为做外贸、受汇率影响没涨」。
我去查，第一轮**按行业知识分组**得出「出口组跑输 15 个百分点」——
然后核实主营构成，发现我把**汇川技术划进了出口型，而它 93.4% 是内销**。

分组是我编的，结论就是假的。

**但「所以不要分类」是矫枉过正** —— 用户当场纠正：
「先分类妈妈才知道是什么吧 问题是分了类里面还有细节而已」。

对。**分类给理解，数字给核验，缺任一个都不行**：

    只有分类 → 无法核验                   = 我一开始犯的错（凭印象分组）
    只有数字 → 「83.5%」是什么意思？       = 我矫过头的错
    分类 + 数字 → 「大部分收入在海外 · 83.5% · 截至2025-12-31财报」

真正的规矩不是「不分类」，是 **分类必须从测量派生，不能从记忆派生**，
而且阈值要写出来、可以被质疑。

## 它说明什么，不说明什么

**说明**：人民币每升值 1%，这部分收入换回人民币就少约 1%。
这是**敞口**，是算术，不是预测。

**不说明**：股价会怎么走。实测 12 只 A 级股，
海外收入占比与 12 个月超额收益的相关系数 **r = −0.18** ——
方向对，但几乎等于噪音。最出口的浙江鼎力（83.5%）是唯一跑赢的，
跌最惨的汇川技术（6.6%）根本不是出口型。

**所以卡片只陈述敞口，不预测涨跌。**

## 数据来源与坑

东财主营构成按「地区」拆分（`stock_zygc_em`）。实测 10 只覆盖 8 只，
2 只抛 KeyError —— 拿不到就**留空**，不猜。

**试过但不可用**：新浪利润表有「汇兑收益」这一列，看起来正是最直接的指标
（财报里真实发生的那笔钱）—— 但实测**值全是 NaN**，列存在而数据不存在。
`列存在 ≠ 数据存在`，这一条值得单独记住。
"""
from __future__ import annotations

# 判断「境内」的关键词。命中则计入国内，其余一律算海外 ——
# 宁可把「其他(补充)」算成海外，也不要漏掉真实的海外收入：
# 低估敞口比高估更危险（会让人以为不受影响）。
_DOMESTIC_KEYS = ("境内", "内地", "国内", "中国大陆", "大陆地区", "中国地区")

# 派生标签的阈值。**写在这里是为了它可以被质疑** ——
# 任何分类都需要一个阈值，藏起来的阈值等于没有依据。
#
# 三档，而且**每一档直接回答用户妈妈问的那个问题**（这只受不受汇率影响），
# 不是泛泛地描述公司。第一版用 40/15 两档，53.4% 的迈瑞被标成
# 「主要做外贸」—— 那其实是海外国内各一半，标签比实际说得大。
_HIGH, _MID = 50.0, 15.0


def _is_domestic(name: str) -> bool:
    n = str(name or "")
    if any(k in n for k in _DOMESTIC_KEYS):
        return True
    # 「中国」单独出现时也算国内，但「中国境外」不算
    return "中国" in n and "境外" not in n and "海外" not in n


def compute(df) -> dict:
    """东财主营构成 DataFrame → {pct, asof, rows} 或 {}。"""
    if df is None or getattr(df, "empty", True):
        return {}
    try:
        reg = df[df["分类类型"].astype(str).str.contains("地区", na=False)]
        if reg.empty:
            return {}
        asof = reg["报告日期"].max()
        latest = reg[reg["报告日期"] == asof]
        dom, total, rows = 0.0, 0.0, []
        for _, r in latest.iterrows():
            try:
                share = float(r["收入比例"])
            except (TypeError, ValueError):
                continue
            nm = str(r["主营构成"])
            total += share
            if _is_domestic(nm):
                dom += share
            rows.append((nm, round(share * 100, 1)))
        if total <= 0 or dom <= 0:
            # 全是海外、或一条都识别不出国内 —— 两种情况都可疑，不给数
            return {}
        return {"pct": round((1 - dom / total) * 100, 1),
                "asof": str(asof)[:10],
                "rows": sorted(rows, key=lambda x: -x[1])[:5]}
    except Exception:
        return {}


def label(pct, locale: str = "zh"):
    """从数字派生标签。**阈值是 _HIGH / _MID，写在模块里可被质疑。**"""
    if pct is None:
        return None
    if locale == "en":
        return ("mostly overseas — FX matters a lot" if pct >= _HIGH else
                ("both, FX matters some" if pct >= _MID else
                 "domestic — FX barely matters"))
    # 措辞要让人一眼知道「这是哪类公司 + 对我问的那件事意味着什么」，
    # 而不是给一个还要自己换算的比例
    return ("海外为主 · 汇率影响大" if pct >= _HIGH else
            ("内外都做 · 汇率有影响" if pct >= _MID else
             "基本只做国内 · 汇率影响很小"))


def describe(pct, asof=None, locale: str = "zh") -> dict:
    """人话。**只说敞口，不说涨跌。**"""
    if pct is None:
        return {}
    if locale == "en":
        return {"headline": label(pct, "en"),
                "figure": f"{pct}% overseas · {round(100 - pct, 1)}% domestic",
                "meaning": (f"If the yuan strengthens 1%, that {pct}% converts back "
                            f"to about 1% less."),
                "asof": f"as of {asof}" if asof else None}
    return {
        # US-216 续：**分类打头**。第一版 headline 是「海外收入 83.5%」——
        # 一个数字，读的人还要自己判断「这算多还是少」。
        "headline": label(pct),
        "figure": f"海外 {pct}% · 国内 {round(100 - pct, 1)}%",
        # 算术，不是预测
        "meaning": (f"人民币每升值 1%，这 {pct}% 的收入换回人民币就少约 1%。"
                    if pct >= _MID else
                    f"只有 {pct}% 的收入来自海外，汇率对它影响很小。"),
        "asof": f"截至 {asof} 财报" if asof else None,
        "label": label(pct),
    }
