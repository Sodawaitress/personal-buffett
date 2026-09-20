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


# ── 财务费用的摆动（US-217）─────────────────────────────────────────────
#
# 用户问「能不能按订单的实时汇率算」。**不能** —— 那是公司内部数据，
# 财报不披露，公开最细只到半年度分地区收入。
#
# **但不用估。** 公司每半年自己报一次财务费用，那个数比我推的准：
#
#     浙江鼎力  我估算「营收拖累 4.5%」
#               实际财务费用增量占营收 **8.42%**   ← 差了快一倍
#
# 因为估算只覆盖**营收换算**，而汇率还打在应收账款和外币资产上，
# 那部分直接进损益。
#
# ⚠️ **不能叫它「汇兑损益」。** 财务费用 = 利息 + 汇兑 + 手续费，拆不开。
# 单独的汇兑字段实测拿不到：
#     新浪利润表「汇兑收益」列          → 值全是 NaN
#     东财 EXCHANGE_INCOME 字段        → 6 家里 1 家有值，且为 0.00 亿
# 所以措辞只能是「财务费用变化（含汇兑）」。少这一步就是过度断言。

_REV_KEYS = ("TOTAL_OPERATE_INCOME", "OPERATE_INCOME")


def finance_swing(df) -> dict:
    """东财利润表 → {cur, prev, delta_rev_pct, asof, kind} 或 {}。

    **必须同口径比**：中报比中报、年报比年报。
    拿 2026 中报去比 2025 年报，会把「半年 vs 全年」的差当成变化 ——
    这是本仓反复栽的那族错误在财务数据上的版本。
    """
    if df is None or getattr(df, "empty", True):
        return {}
    try:
        import math
        d = df.copy()
        d["_date"] = d["REPORT_DATE"].astype(str).str[:10]
        d["_md"] = d["_date"].str[5:]
        latest = d.iloc[0]
        md = str(latest["_md"])
        same = d[d["_md"] == md]           # 同口径：同样的月-日
        if len(same) < 2:
            return {}
        cur, prev = same.iloc[0], same.iloc[1]

        def _f(row, key):
            try:
                v = float(row[key])
                return None if math.isnan(v) else v
            except (TypeError, ValueError, KeyError):
                return None

        fe0, fe1 = _f(cur, "FINANCE_EXPENSE"), _f(prev, "FINANCE_EXPENSE")
        if fe0 is None or fe1 is None:
            return {}
        rev = next((_f(cur, k) for k in _REV_KEYS if _f(cur, k)), None)
        if not rev or rev <= 0:
            return {}
        return {
            "cur": round(fe0 / 1e8, 2),
            "prev": round(fe1 / 1e8, 2),
            "delta_rev_pct": round((fe0 - fe1) / rev * 100, 2),
            "asof": str(cur["_date"]),
            "prev_asof": str(prev["_date"]),
            "kind": str(cur.get("REPORT_TYPE") or ""),
            # 从「赚钱」翻成「花钱」是最值得说出来的那个变化
            "flipped": fe1 < 0 <= fe0,
        }
    except Exception:
        return {}


def describe_swing(sw: dict, fx_pct=None, locale: str = "zh") -> dict:
    """人话。**只说财务费用，不说汇兑损益。**"""
    if not sw:
        return {}
    if locale == "en":
        head = (f"financial costs swung by {sw['delta_rev_pct']:+.2f}% of revenue")
        return {"headline": head,
                "detail": f"{sw['prev']}亿 → {sw['cur']}亿 ({sw['kind']})",
                "caveat": ("Financial expense = interest + FX + fees; "
                           "the FX line alone is not available.")}
    flip = ("去年这一项在**赚钱**，今年变成了净支出。"
            if sw.get("flipped") else "")
    fx = (f"同期人民币升值 {fx_pct:.1f}%。" if fx_pct and fx_pct > 0 else
          (f"同期人民币贬值 {abs(fx_pct):.1f}%。" if fx_pct else ""))
    return {
        "headline": f"财务费用增量相当于营收的 {sw['delta_rev_pct']:+.2f}%",
        "detail": f"{sw['prev']}亿 → {sw['cur']}亿（{sw['kind']}，同口径比上年）",
        "flip": flip,
        "fx": fx,
        "caveat": ("财务费用 = 利息 + 汇兑 + 手续费，**拆不开**。"
                   "单独的汇兑那一项，财报接口拿不到。"),
    }


# ── 汇率影响的三层（US-218）────────────────────────────────────────────
#
# 用户问「影响的层次」。这正好是国际财务管理的标准分类，
# 而且三层**按时间排序**：
#
#   ① 交易敞口 transaction  签约 → 收款之间汇率变了     数周~数月
#   ② 折算敞口 translation  合并报表时的账面换算         每个报告期
#   ③ 经济敞口 economic     人民币贵了，东西卖不动       数季度~数年
#
# 用户上一个问题「能不能按订单实时汇率算」问的正是 **① 层** ——
# 现在能说清为什么拿不到：那是交易敞口，财报不披露。
#
# 而 ③ 层是**最大但最慢**的：它不进财务费用，它直接吃掉订单。
#
# ## 三层的展示规则（都有依据，不是拍的）
#
# **① 明确显示「算不出」，不要省略。** 那一层的缺失本身就是答案。
#
# **② 最醒目** —— 它是报出来的数。
#
# **③ 视觉上最淡。** 这条和直觉相反：我本来想把估算「标出来」让它更显眼，
# 方向错了。可视化研究的规则是
# 「对一个估算越没把握，就让它在视觉上越不突出，
#   这样更确定的数据才会得到更多注意」。
#
# **来源标记融进显示本身**（【报出来的数】/〔估算〕），不做脚注 ——
# 「数据来源的可视化应当无缝融进看板」。
#
# ## 不用瀑布图
#
# 收入桥/瀑布图是业界分解因果的标准画法，但对新手读者有两个**内在**障碍：
# 正值从下往上读、负值从上往下读；中间分项没有共同基准轴。
# 128 人的研究里参与者可视化熟悉度平均 2.09/5，瀑布图正是难点之一。
# 本站主要读者是年长非专业的手机用户 —— 用现有的「横条 + 文字」。


def constant_currency(rev_yoy, overseas_pct, fx_pct):
    """恒定汇率下的营收增速（**估算**）。

        恒定汇率增速 ≈ 报告增速 + 海外占比 × 汇率变动

    业界标准做法是把本期数字按上期平均汇率重算一遍。我们没有分币种的
    原币收入，只能用这个一阶近似 —— **所以它必须被标成估算**。

    实测：浙江鼎力报告 +24.9%，恒定汇率下约 +29.4%
    （汇率拿走约 4.5 个百分点，但它即使这样还是涨了 24.9%）。
    阳光电源 −29.0% → −25.0%，**汇率解释不了它的下跌**。
    """
    if rev_yoy is None or overseas_pct is None or fx_pct is None:
        return None
    return round(rev_yoy + overseas_pct / 100 * fx_pct, 1)


def fx_layers(overseas_pct=None, swing=None, rev_yoy=None, fx_pct=None,
              locale: str = "zh", fx_pending_pct=None, pending_label=None) -> dict:
    """三层装配。每层带 `certainty`：measured / estimated / unavailable。

    `certainty` 直接驱动视觉层级 —— 越不确定越淡。
    """
    if fx_pct is None:
        return {}
    cc = constant_currency(rev_yoy, overseas_pct, fx_pct)
    taken = (round(cc - rev_yoy, 1)
             if cc is not None and rev_yoy is not None else None)
    zh = locale != "en"
    layers = []
    # US-219：最新的排最前（位置 = 时间），但视觉上和第③层一样淡
    # （强度 = 确定性）。两个维度两种编码，否则「最新」会被读成「最重要」。
    _p = pending_layer(overseas_pct, fx_pending_pct, pending_label, locale)
    if _p:
        layers.append(_p)
    layers += [
        {"n": 1, "certainty": "unavailable",
         "name": "订单层" if zh else "Transaction",
         "sub": "签约到收款之间" if zh else "contract → settlement",
         "value": None,
         "note": ("财报不披露 —— 这一层算不出" if zh
                  else "not disclosed — cannot be computed")},
    ]
    if swing and swing.get("delta_rev_pct") is not None:
        layers.append({
            "n": 2, "certainty": "measured",
            "name": "账面层" if zh else "Translation",
            "sub": "合并报表换算" if zh else "consolidation",
            "value": f"{swing['delta_rev_pct']:+.2f}%",
            "detail": (f"财务费用 {swing['prev']}亿 → {swing['cur']}亿" if zh
                       else f"finance cost {swing['prev']} → {swing['cur']}"),
            "note": "增量相当于营收的比例" if zh else "as % of revenue",
            "tag": "报出来的数" if zh else "reported",
        })
    if cc is not None:
        layers.append({
            "n": 3, "certainty": "estimated",
            "name": "生意层" if zh else "Economic",
            "sub": "东西贵了卖不动" if zh else "competitiveness",
            "value": f"{cc:+.1f}%",
            "detail": (f"营收 {rev_yoy:+.1f}%，剔掉汇率约 {cc:+.1f}%" if zh
                       else f"revenue {rev_yoy:+.1f}%, ex-FX ≈ {cc:+.1f}%"),
            "note": (f"汇率大约拿走 {abs(taken):.1f} 个百分点" if zh and taken
                     else None),
            "tag": "估算" if zh else "estimate",
        })
    return {"fx_pct": fx_pct, "layers": layers,
            "has_pending": bool(_p),
            "fx_text": ((f"同期人民币升值 {fx_pct:.1f}%" if fx_pct > 0
                         else f"同期人民币贬值 {abs(fx_pct):.1f}%") if zh
                        else f"CNY {'+' if fx_pct > 0 else ''}{fx_pct:.1f}%")}


def pending_layer(overseas_pct, fx_pending_pct, asof_label=None,
                  locale: str = "zh"):
    """本期至今、**还没进任何财报**的那一段（US-219）。

    用户的批评：「你这些都是事后分析了，已经涨了的，市场预期已经搞了不是吗」。

    **对。** 财务费用来自 2026 中报，8 月就公布了，市场早消化了。
    但汇率是**每天可观测**的，而本期的账要等下一份财报才披露 ——
    这一段卡在「已经发生在账上」和「还没人报出来」之间。

    ## 但它不是买卖信号，三条限制必须跟着一起显示

    ① 汇率是公开的，这个算术谁都能做，别假设市场没注意到
    ② 实测海外占比与 12 个月超额收益 **r = −0.18**，几乎是噪音 ——
       海外占比最高的浙江鼎力还是唯一跑赢的那只
    ③ 它是估算，真实数字要等年报

    **它防的不是「错过机会」，是「归错因」。** 归错因会让人抱着一个
    坏理由继续持有 —— 比如以为阳光电源跌是因为汇率，等汇率转向就会涨，
    而实际上剔掉汇率它还是 −25%。

    ## 视觉编码：位置 = 时间，强度 = 确定性

    它排在最前面（最新），但**和第③层一样淡**（同样是估算）。
    两个维度用两种编码，互不干扰 —— 否则「最新」会被读成「最重要」。
    """
    if overseas_pct is None or fx_pending_pct is None:
        return None
    drag = round(overseas_pct / 100 * fx_pending_pct, 1)
    zh = locale != "en"
    if zh:
        return {
            "n": 0, "certainty": "estimated", "pending": True,
            "name": "本期至今", "sub": "还没进财报",
            "value": f"{drag:+.1f}%",
            "detail": (f"人民币已{'升值' if fx_pending_pct > 0 else '贬值'} "
                       f"{abs(fx_pending_pct):.1f}%，按海外 {overseas_pct}% 推算"),
            "note": (f"约 {abs(drag):.1f}% 的{'拖累' if drag > 0 else '助力'}"
                     f"正在累积" + (f"，{asof_label}" if asof_label else "")),
            "tag": "估算",
        }
    return {"n": 0, "certainty": "estimated", "pending": True,
            "name": "This period", "sub": "not yet reported",
            "value": f"{drag:+.1f}%", "tag": "estimate",
            "detail": f"CNY {fx_pending_pct:+.1f}% × {overseas_pct}% overseas"}
