"""US-216：这只股票有多少收入来自海外。

**起因**：用户妈妈说「有些评级 A 的票因为做外贸、受汇率影响没涨」。
我去查，第一轮**按行业知识分组**得出「出口组跑输 15 个百分点」——
然后核实主营构成，发现我把**汇川技术划进了出口型，而它 93.4% 是内销**。

分组是我编的，结论就是假的。

**所以这个模块不做分类。** 它只存一个数字：海外收入占比。
需要标签时从数字派生，并且把阈值写出来。

    ❌ 「出口型」          ← 谁定的？阈值多少？
    ✅ 「海外收入 83.5%」  ← 可核验，来源是财报

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
_HIGH, _MID = 40.0, 15.0


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
        return ("mostly overseas" if pct >= _HIGH else
                ("partly overseas" if pct >= _MID else "mostly domestic"))
    return ("大部分收入在海外" if pct >= _HIGH else
            ("有一部分海外收入" if pct >= _MID else "主要做国内"))


def describe(pct, asof=None, locale: str = "zh") -> dict:
    """人话。**只说敞口，不说涨跌。**"""
    if pct is None:
        return {}
    if locale == "en":
        return {"headline": f"{pct}% of revenue is from overseas",
                "meaning": (f"If the yuan strengthens 1%, that {pct}% converts back "
                            f"to about 1% less."),
                "asof": f"as of {asof}" if asof else None}
    return {
        "headline": f"海外收入 {pct}%",
        # 算术，不是预测
        "meaning": (f"人民币每升值 1%，这 {pct}% 的收入换回人民币就少约 1%。"
                    if pct >= _MID else
                    f"只有 {pct}% 的收入来自海外，汇率对它影响很小。"),
        "asof": f"截至 {asof} 财报" if asof else None,
        "label": label(pct),
    }
