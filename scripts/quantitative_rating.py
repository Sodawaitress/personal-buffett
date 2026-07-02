#!/usr/bin/env python3
"""
定量化巴菲特评级系统
完全基于财务数据，无需 LLM
所有规则来自 buffett_analyst.py 中的既有框架
"""

import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# ─────────────────────────────────────────────────────────
# Translations  (human-language descriptions, not jargon)
# ─────────────────────────────────────────────────────────

_T: Dict[str, Dict[str, str]] = {
    "zh": {
        # ── score_roe ──────────────────────────────────────────
        "roe_exceptional":         "顶级赚钱机器——投入100元就能赚回25元以上，这是很强护城河的标志",
        "roe_excellent":           "优秀赚钱能力——投入100元能赚回20元以上",
        "roe_good":                "不错的赚钱能力——投入100元能赚回15元以上",
        "roe_average":             "一般赚钱能力——投入100元赚回约10元",
        "roe_weak":                "赚钱能力偏弱——投入100元只能赚回5-10元",
        "roe_near_zero":           "⚠️ 几乎没有赚钱能力——投入100元连5元都赚不到",
        "roe_negative":            "🚨 公司当前在亏损——投进去的本金在缩水",

        # ── score_net_margin ───────────────────────────────────
        "margin_exceptional":      "极强定价权——卖100元东西，能留下25元以上的利润",
        "margin_strong":           "很强定价权——卖100元东西，能留下15元以上",
        "margin_moderate":         "中等定价权——卖100元东西，能留约10元",
        "margin_weak":             "定价权偏弱——卖100元东西，只能留5-10元",
        "margin_very_weak":        "定价权很弱——卖100元东西，利润还不到5元",
        "margin_negative":         "🚨 卖东西不赚钱——销售额越多亏得越多",

        # ── score_roe_stability ────────────────────────────────
        "stability_data_short":    "数据年份太少，无法判断稳定性",
        "stability_very_stable":   "盈利能力非常稳定——年年如此，不是靠某年运气",
        "stability_stable":        "盈利能力比较稳定——有小幅波动，但整体可预测",
        "stability_moderate":      "盈利能力有些波动——好年坏年差异较明显",
        "stability_volatile":      "盈利能力波动较大——好年坏年差异很大",
        "stability_high_volatile": "⚠️ 盈利极不稳定——像过山车，很难预测",

        # ── score_fcf_quality ──────────────────────────────────
        "fcf_data_missing":        "现金流数据缺失，无法验证利润的真实性",
        "fcf_excellent":           "利润是真实的现金，不是会计上的数字游戏",
        "fcf_good":                "利润质量不错——基本上赚到的钱都有真实现金流入",
        "fcf_average":             "利润质量一般——部分利润可能只是账面数字，未必有现金",
        "fcf_poor":                "⚠️ 利润质量差——账面上赚钱，但现金可能并不够用",

        # ── dimension labels ───────────────────────────────────
        "moat_data_insufficient":  "护城河数据不足",
        "moat_roe_label":          "赚钱能力（ROE）",
        "moat_margin_label":       "利润率",
        "moat_stability_label":    "盈利稳定性",
        "moat_fcf_label":          "利润真实性",
        "pts":                     "分",
        "data_insufficient":       "数据不足",
        "data_missing":            "数据缺失",

        # ── score_profit_growth ────────────────────────────────
        "growth_data_short":       "财务数据年份不足，无法计算增速",
        "growth_loss_years":       "有亏损年份，利润增速在这里没有意义",
        "growth_high":             "高速增长——利润每年平均增加{cagr:.1f}%，明显超行业",
        "growth_fast":             "快速增长——利润每年平均增加{cagr:.1f}%",
        "growth_good":             "稳健增长——利润每年平均增加{cagr:.1f}%",
        "growth_moderate":         "温和增长——利润每年平均增加{cagr:.1f}%",
        "growth_slow":             "增长缓慢——利润每年平均只增加{cagr:.1f}%",
        "growth_declining":        "🚨 利润在萎缩——每年平均减少{cagr:.1f}%",

        # ── score_profit_consistency ───────────────────────────
        "consist_data_short":      "数据不足3年，无法判断一致性",
        "consist_consistent":      "过去3年持续盈利，没有亏损年",
        "consist_mostly":          "基本盈利，但3年里有1年出现了亏损",
        "consist_weak":            "⚠️ 3年里有2年亏损，盈利很不稳定",
        "consist_consecutive":     "🚨 3年连续亏损",

        # ── score_management ───────────────────────────────────
        "mgmt_buyback":            "公司在用自己的钱回购股票——对股东友好的信号",
        "mgmt_dividend":           "有分红计划——公司愿意把利润分给股东",
        "mgmt_resignation":        "🚨 CEO或CFO近期离职——关键管理层离开是预警信号",
        "mgmt_reduction":          "管理层在卖出自家股票——内部人对前景不够有信心",
        "mgmt_neutral":            "没有明显的管理层正面或负面信号",

        # ── growth_and_management labels ──────────────────────
        "growth_label":            "利润增速",
        "consist_label":           "盈利一致性",
        "profit_data_label":       "利润数据",
        "mgmt_label":              "管理层信号",

        # ── score_debt ─────────────────────────────────────────
        "debt_very_low":           "几乎不借债——财务非常保守，抗风险能力强",
        "debt_low":                "借债很少——财务健康，风险低",
        "debt_moderate":           "适度借债——处于可接受范围，但要关注",
        "debt_elevated":           "借债较多——还款压力在增加，需要留意",
        "debt_high":               "⚠️ 借债很多——利率上升或收入下降都可能带来麻烦",
        "debt_extreme":            "🚨 极度高杠杆——借的钱超过自有资产2倍，财务风险极高",

        # ── score_profitability_sustainability ─────────────────
        "sust_data_short":         "数据不足3年",
        "sust_strong":             "过去3年都在盈利——这不是一次性的",
        "sust_fair":               "3年里有2年盈利，基本能维持",
        "sust_weak":               "⚠️ 3年里只有1年盈利——持续赚钱的能力存疑",
        "sust_bankruptcy":         "🚨 持续亏损——破产风险显著",

        # ── score_safety labels ────────────────────────────────
        "safety_data_insufficient": "安全性数据不足",
        "debt_label":              "借债风险",
        "sust_label":              "持续盈利能力",

        # ── score_pe_valuation ─────────────────────────────────
        "pe_data_missing":         "PE估值数据缺失",
        "pe_cheap":                "便宜——跟自己历史价格比，现在处于很低的位置",
        "pe_fairly_cheap":         "略便宜——比自己历史上大多数时候都便宜",
        "pe_fair":                 "正常估值——和自己历史平均价格差不多",
        "pe_fairly_expensive":     "⚠️ 偏贵——比自己历史上大多数时候都贵",
        "pe_expensive":            "🚨 很贵——比自己历史价格的大多数时候都贵很多",

        # ── score_pb_valuation ─────────────────────────────────
        "pb_data_missing":         "PB估值数据缺失",
        "pb_cheap":                "按资产算也便宜",
        "pb_fairly_cheap":         "按资产算略便宜",
        "pb_fair":                 "按资产算正常",
        "pb_fairly_expensive":     "⚠️ 按资产算略贵",
        "pb_expensive":            "按资产算贵",

        # ── score_price_position ───────────────────────────────
        "pos_data_missing":        "价格位置数据缺失",
        "pos_near_high":           "🚨 当前价格接近52周最高点——现在买入风险较大",
        "pos_near_high_mild":      "⚠️ 当前价格比较靠近今年高点",
        "pos_near_low":            "当前价格接近52周最低点——历史上比较划算的入场区域",
        "pos_near_low_mild":       "当前价格处于今年低位区域",
        "pos_mid":                 "当前价格处于今年价格区间中段",

        # ── score_valuation labels ─────────────────────────────
        "pe_label":                "PE估值",
        "pb_label":                "PB估值",
        "pos_label":               "价格位置",

        # ── get_grade_and_conclusion ───────────────────────────
        "grade_a_desc":            "很少见的好机会——公司优秀，价格还便宜",
        "grade_bplus_desc":        "不错的公司，价格合理",
        "grade_b_desc":            "普通公司，价格也是普通价",
        "grade_bminus_desc":       "低于平均的公司，需要继续观察",
        "grade_cplus_desc":        "有明显风险信号，暂时不适合买入",
        "grade_c_desc":            "问题较多，持有要控制仓位",
        "grade_d_desc":            "高危，建议优先考虑退出",

        # ── extract_red_flags ──────────────────────────────────
        "flag_roe_low":            "🚨 投入100元赚不到5元（ROE < 5%）——赚钱能力几乎为零",
        "flag_roe_negative":       "🚨 公司当前在亏损（ROE < 0%）",
        "flag_margin_negative":    "🚨 卖东西不赚钱——净利率为负",
        "flag_debt_extreme":       "🚨 借的钱超过自有资产2倍——极高财务风险",
        "flag_price_high":         "🚨 价格处于今年{pct:.0f}%分位，接近最高点",
        "flag_consecutive_loss":   "🚨 连续3年亏损——破产风险不可忽视",
        "flag_resignation":        "🚨 CEO/CFO近期离职——管理层稳定性存疑",
        "flag_fund_outflow":       "🚨 主力资金正在大量离场",

        # ── rate_stock reasoning ───────────────────────────────
        "reasoning_template":      "综合得分 {score}/100：{desc}",
        "reasoning_risk":          "⚠️ 风险：{flag}",
    },

    "en": {
        # ── score_roe ──────────────────────────────────────────
        "roe_exceptional":         "Top-tier money machine — earns 25%+ for every dollar invested; a sign of strong competitive moat",
        "roe_excellent":           "Excellent earning power — earns 20%+ return on capital",
        "roe_good":                "Good earning power — earns 15%+ on capital invested",
        "roe_average":             "Average earning power — earns around 10% on capital",
        "roe_weak":                "Weak earning power — earns only 5–10% on capital",
        "roe_near_zero":           "⚠️ Near-zero returns — earns less than 5% on capital invested",
        "roe_negative":            "🚨 Losing money — capital is shrinking, not growing",

        # ── score_net_margin ───────────────────────────────────
        "margin_exceptional":      "Exceptional pricing power — keeps 25%+ profit from every dollar in sales",
        "margin_strong":           "Strong pricing power — keeps 15%+ from each dollar in sales",
        "margin_moderate":         "Moderate pricing power — keeps around 10% from sales",
        "margin_weak":             "Thin margins — keeps only 5–10¢ per dollar in sales",
        "margin_very_weak":        "Very thin margins — barely keeps less than 5¢ per dollar in sales",
        "margin_negative":         "🚨 Selling at a loss — the more it sells, the more it loses",

        # ── score_roe_stability ────────────────────────────────
        "stability_data_short":    "Not enough years of data to judge consistency",
        "stability_very_stable":   "Rock-solid consistency — earns the same reliably every year, not just lucky once",
        "stability_stable":        "Fairly steady — minor swings but broadly predictable",
        "stability_moderate":      "Some variability — noticeable differences between good and bad years",
        "stability_volatile":      "Volatile — big swings between good and bad years",
        "stability_high_volatile": "⚠️ Highly unpredictable — earnings swing wildly, very hard to forecast",

        # ── score_fcf_quality ──────────────────────────────────
        "fcf_data_missing":        "Cash flow data unavailable — can't verify whether profits are real",
        "fcf_excellent":           "Profits are real cash, not accounting tricks",
        "fcf_good":                "Good profit quality — earnings are mostly backed by actual cash inflows",
        "fcf_average":             "Average quality — some profits may not convert to actual cash",
        "fcf_poor":                "⚠️ Profits look good on paper but cash may be tight",

        # ── dimension labels ───────────────────────────────────
        "moat_data_insufficient":  "Insufficient moat data",
        "moat_roe_label":          "Earning power (ROE)",
        "moat_margin_label":       "Profit margin",
        "moat_stability_label":    "Earnings stability",
        "moat_fcf_label":          "Profit quality",
        "pts":                     "pts",
        "data_insufficient":       "Insufficient data",
        "data_missing":            "Data unavailable",

        # ── score_profit_growth ────────────────────────────────
        "growth_data_short":       "Not enough data to calculate growth rate",
        "growth_loss_years":       "Contains loss years — growth rate not meaningful here",
        "growth_high":             "High growth — profits compounding at {cagr:.1f}%/yr, well above average",
        "growth_fast":             "Fast growth — profits up {cagr:.1f}% per year on average",
        "growth_good":             "Solid growth — {cagr:.1f}% per year on average",
        "growth_moderate":         "Moderate growth — {cagr:.1f}% per year",
        "growth_slow":             "Slow growth — only {cagr:.1f}% per year",
        "growth_declining":        "🚨 Shrinking profits — declining at {cagr:.1f}% per year",

        # ── score_profit_consistency ───────────────────────────
        "consist_data_short":      "Less than 3 years of data",
        "consist_consistent":      "Profitable every year for the past 3 years — no loss years",
        "consist_mostly":          "Mostly profitable, but had 1 loss year in the past 3",
        "consist_weak":            "⚠️ Lost money 2 out of the last 3 years",
        "consist_consecutive":     "🚨 Lost money all 3 years in a row",

        # ── score_management ───────────────────────────────────
        "mgmt_buyback":            "Company buying back its own shares — a shareholder-friendly move",
        "mgmt_dividend":           "Paying dividends — sharing profits with shareholders",
        "mgmt_resignation":        "🚨 CEO or CFO recently left — losing key leaders is a warning sign",
        "mgmt_reduction":          "Management selling their own shares — insiders not confident in the stock",
        "mgmt_neutral":            "No notable positive or negative management signals",

        # ── growth_and_management labels ──────────────────────
        "growth_label":            "Profit growth",
        "consist_label":           "Earnings consistency",
        "profit_data_label":       "Profit data",
        "mgmt_label":              "Management signals",

        # ── score_debt ─────────────────────────────────────────
        "debt_very_low":           "Barely any debt — very conservative, resilient in downturns",
        "debt_low":                "Low debt — healthy balance sheet, minimal financial risk",
        "debt_moderate":           "Moderate borrowing — acceptable, but worth keeping an eye on",
        "debt_elevated":           "Elevated debt — repayment pressure is building",
        "debt_high":               "⚠️ Heavy debt — rate rises or a slowdown could cause serious trouble",
        "debt_extreme":            "🚨 Extreme leverage — borrowed far more than it owns, very high financial risk",

        # ── score_profitability_sustainability ─────────────────
        "sust_data_short":         "Less than 3 years of data",
        "sust_strong":             "Profitable all 3 years — this isn't a one-time thing",
        "sust_fair":               "Profitable 2 of 3 years — mostly sustainable",
        "sust_weak":               "⚠️ Only 1 profitable year out of 3 — sustainability in doubt",
        "sust_bankruptcy":         "🚨 Persistent losses — significant bankruptcy risk",

        # ── score_safety labels ────────────────────────────────
        "safety_data_insufficient": "Insufficient safety data",
        "debt_label":              "Debt risk",
        "sust_label":              "Earnings sustainability",

        # ── score_pe_valuation ─────────────────────────────────
        "pe_data_missing":         "PE data unavailable",
        "pe_cheap":                "Cheap — near the low end of its own price history",
        "pe_fairly_cheap":         "Fairly cheap — cheaper than most of its own history",
        "pe_fair":                 "Fair value — roughly in line with its own historical average",
        "pe_fairly_expensive":     "⚠️ On the pricey side — more expensive than usual for this stock",
        "pe_expensive":            "🚨 Expensive — pricier than almost all of its own price history",

        # ── score_pb_valuation ─────────────────────────────────
        "pb_data_missing":         "PB data unavailable",
        "pb_cheap":                "Cheap on an asset basis",
        "pb_fairly_cheap":         "Fairly cheap on an asset basis",
        "pb_fair":                 "Fair on an asset basis",
        "pb_fairly_expensive":     "⚠️ Slightly expensive on an asset basis",
        "pb_expensive":            "Expensive on an asset basis",

        # ── score_price_position ───────────────────────────────
        "pos_data_missing":        "Price position data unavailable",
        "pos_near_high":           "🚨 Near the 52-week high — risky time to buy",
        "pos_near_high_mild":      "⚠️ Fairly close to the yearly high",
        "pos_near_low":            "Near the 52-week low — historically an attractive entry zone",
        "pos_near_low_mild":       "In the lower range of this year's prices",
        "pos_mid":                 "Mid-range within this year's price band",

        # ── score_valuation labels ─────────────────────────────
        "pe_label":                "PE valuation",
        "pb_label":                "PB valuation",
        "pos_label":               "Price position",

        # ── get_grade_and_conclusion ───────────────────────────
        "grade_a_desc":            "Rare combination — excellent business at a cheap price",
        "grade_bplus_desc":        "Good business at a fair price",
        "grade_b_desc":            "Average business at an average price",
        "grade_bminus_desc":       "Below-average business, needs monitoring",
        "grade_cplus_desc":        "Notable risk signals — not a good time to buy",
        "grade_c_desc":            "Multiple issues — keep position size in check",
        "grade_d_desc":            "High risk — consider exiting this position",

        # ── extract_red_flags ──────────────────────────────────
        "flag_roe_low":            "🚨 Earns less than 5¢ per dollar invested (ROE < 5%) — near-zero earning power",
        "flag_roe_negative":       "🚨 Company is currently losing money (ROE < 0%)",
        "flag_margin_negative":    "🚨 Selling at a loss — negative profit margin",
        "flag_debt_extreme":       "🚨 Debt exceeds 2× equity — extreme financial risk",
        "flag_price_high":         "🚨 Price at {pct:.0f}% of 52-week range — near yearly high",
        "flag_consecutive_loss":   "🚨 3 consecutive loss years — bankruptcy risk can't be ignored",
        "flag_resignation":        "🚨 CEO/CFO recently left — leadership stability uncertain",
        "flag_fund_outflow":       "🚨 Large institutional outflows detected",

        # ── rate_stock reasoning ───────────────────────────────
        "reasoning_template":      "Score {score}/100: {desc}",
        "reasoning_risk":          "⚠️ Risk: {flag}",
    },
}


def _pct(value, default=0.0) -> float:
    """安全地把 '15.3%' 或 15.3 (float/int) 都转成 float。
    None 和空字符串返回 default；其他无法解析的值也返回 default。
    注意：真实的 0 值（如 '0.0'、'0%'）返回 0.0，不视为缺失。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return float(default)
    try:
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return float(default)


def _t(key: str, locale: str = "zh") -> str:
    """Look up a translated string; fall back to zh then the key itself."""
    d = _T.get(locale if locale in _T else "zh", _T["zh"])
    return d.get(key) or _T["zh"].get(key, key)


class QuantitativeRater:
    """基于数据的巴菲特评级引擎"""

    def __init__(self):
        pass

    # ─────────────────────────────────────────────────────────
    # 第一维：护城河评分 (40 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_roe(roe_pct: float, locale: str = "zh") -> Tuple[int, str]:
        """ROE 评分 (15 分)"""
        if roe_pct > 25:
            return 15, _t("roe_exceptional", locale)
        elif roe_pct > 20:
            return 13, _t("roe_excellent", locale)
        elif roe_pct > 15:
            return 10, _t("roe_good", locale)
        elif roe_pct > 10:
            return 7, _t("roe_average", locale)
        elif roe_pct > 5:
            return 3, _t("roe_weak", locale)
        elif roe_pct >= 0:
            return 0, _t("roe_near_zero", locale)
        else:
            return -5, _t("roe_negative", locale)

    @staticmethod
    def score_net_margin(margin_pct: float, locale: str = "zh") -> Tuple[int, str]:
        """净利率评分 (10 分)"""
        if margin_pct > 25:
            return 10, _t("margin_exceptional", locale)
        elif margin_pct > 15:
            return 8, _t("margin_strong", locale)
        elif margin_pct > 10:
            return 6, _t("margin_moderate", locale)
        elif margin_pct > 5:
            return 4, _t("margin_weak", locale)
        elif margin_pct >= 0:
            return 2, _t("margin_very_weak", locale)
        else:
            return -5, _t("margin_negative", locale)

    @staticmethod
    def score_roe_stability(roe_list: List[float], locale: str = "zh") -> Tuple[int, str]:
        """ROE 稳定性评分 (10 分)"""
        if len(roe_list) < 2:
            return 5, _t("stability_data_short", locale)

        avg_roe = sum(roe_list) / len(roe_list)
        if avg_roe == 0:
            volatility = float('inf')
        else:
            variance = sum((x - avg_roe) ** 2 for x in roe_list) / len(roe_list)
            std_dev = variance ** 0.5
            volatility = std_dev / abs(avg_roe)

        if volatility < 0.10:
            return 10, _t("stability_very_stable", locale)
        elif volatility < 0.20:
            return 8, _t("stability_stable", locale)
        elif volatility < 0.30:
            return 5, _t("stability_moderate", locale)
        elif volatility < 0.50:
            return 3, _t("stability_volatile", locale)
        else:
            return -3, _t("stability_high_volatile", locale)

    @staticmethod
    def score_fcf_quality(fcf_ratio: Optional[float], locale: str = "zh") -> Tuple[int, str]:
        """现金流质量评分 (5 分)"""
        if fcf_ratio is None:
            return 3, _t("fcf_data_missing", locale)

        if fcf_ratio >= 1.0:
            return 5, _t("fcf_excellent", locale)
        elif fcf_ratio >= 0.8:
            return 4, _t("fcf_good", locale)
        elif fcf_ratio >= 0.5:
            return 2, _t("fcf_average", locale)
        else:
            return -2, _t("fcf_poor", locale)

    @classmethod
    def score_moat(cls, annual_data: List[Dict], locale: str = "zh", signals: Dict = None) -> Tuple[int, List[str]]:
        """护城河总分 (40 分)"""
        details = []
        total = 0
        pts = _t("pts", locale)

        if not annual_data and not signals:
            return 0, [_t("moat_data_insufficient", locale)]

        if annual_data:
            latest = annual_data[0]
            roe_pct = _pct(latest.get("roe"))
            margin_pct = _pct(latest.get("net_margin"))
        else:
            # 非A股无年报时，用 yfinance 实时财务指标作 fallback
            roe_val = signals.get("roe") if signals else None
            margin_val = signals.get("profit_margin") if signals else None
            roe_pct = roe_val * 100 if roe_val is not None else 0
            margin_pct = margin_val * 100 if margin_val is not None else 0
            annual_data = []  # 后续稳定性/FCF逻辑安全退化

        roe_score, roe_desc = cls.score_roe(roe_pct, locale)
        details.append(f"{_t('moat_roe_label', locale)}: {roe_score}/15 {pts} — {roe_desc}")
        total += roe_score

        margin_score, margin_desc = cls.score_net_margin(margin_pct, locale)
        details.append(f"{_t('moat_margin_label', locale)}: {margin_score}/10 {pts} — {margin_desc}")
        total += margin_score

        roe_list = [_pct(y.get("roe")) for y in annual_data[:5]]
        stability_score, stability_desc = cls.score_roe_stability(roe_list, locale)
        details.append(f"{_t('moat_stability_label', locale)}: {stability_score}/10 {pts} — {stability_desc}")
        total += stability_score

        if annual_data and "ocf_per_share" in annual_data[0] and "eps" in annual_data[0]:
            latest = annual_data[0]
            try:
                ocf = float(latest["ocf_per_share"])
                eps = float(latest["eps"])
                fcf_ratio = ocf / eps if eps != 0 else None
                fcf_score, fcf_desc = cls.score_fcf_quality(fcf_ratio, locale)
                details.append(f"{_t('moat_fcf_label', locale)}: {fcf_score}/5 {pts} — {fcf_desc}")
                total += fcf_score
            except Exception:
                total += 3
                details.append(f"{_t('moat_fcf_label', locale)}: 3/5 {pts} — {_t('data_insufficient', locale)}")
        else:
            total += 3
            details.append(f"{_t('moat_fcf_label', locale)}: 3/5 {pts} — {_t('data_missing', locale)}")

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第二维：增长与管理层 (25 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_profit_growth(profit_list: List[float], years: int = 3, locale: str = "zh") -> Tuple[int, str]:
        """利润增长评分 (12 分)"""
        if len(profit_list) < 2:
            return 0, _t("growth_data_short", locale)

        recent = profit_list[:years]
        if recent[0] <= 0 or recent[-1] <= 0:
            return 0, _t("growth_loss_years", locale)

        cagr = (recent[0] / recent[-1]) ** (1 / (len(recent) - 1)) - 1
        cagr_pct = cagr * 100

        if cagr_pct > 30:
            return 12, _t("growth_high", locale).format(cagr=cagr_pct)
        elif cagr_pct > 15:
            return 10, _t("growth_fast", locale).format(cagr=cagr_pct)
        elif cagr_pct > 10:
            return 8, _t("growth_good", locale).format(cagr=cagr_pct)
        elif cagr_pct > 5:
            return 5, _t("growth_moderate", locale).format(cagr=cagr_pct)
        elif cagr_pct >= 0:
            return 2, _t("growth_slow", locale).format(cagr=cagr_pct)
        else:
            return -5, _t("growth_declining", locale).format(cagr=cagr_pct)

    @staticmethod
    def score_profit_consistency(profit_list: List[float], locale: str = "zh") -> Tuple[int, str]:
        """利润增长一致性评分 (8 分)"""
        if len(profit_list) < 3:
            return 4, _t("consist_data_short", locale)

        recent_3y = profit_list[:3]
        negative_count = sum(1 for p in recent_3y if p < 0)

        if negative_count == 0:
            return 8, _t("consist_consistent", locale)
        elif negative_count == 1:
            return 5, _t("consist_mostly", locale)
        elif negative_count == 2:
            return 1, _t("consist_weak", locale)
        else:
            return -5, _t("consist_consecutive", locale)

    @staticmethod
    def score_management(news_signals: Dict, locale: str = "zh") -> Tuple[int, str]:
        """管理层信号评分 (5 分)"""
        score = 2
        reasons = []

        if news_signals.get("high_pos_buyback", 0) > 0:
            score += 2
            reasons.append(_t("mgmt_buyback", locale))
        elif news_signals.get("mid_pos_dividend", 0) > 0:
            score += 1
            reasons.append(_t("mgmt_dividend", locale))

        if news_signals.get("high_neg_resignation", 0) > 0:
            score -= 2
            reasons.append(_t("mgmt_resignation", locale))

        if news_signals.get("mid_neg_reduction", 0) > 0:
            score -= 1
            reasons.append(_t("mgmt_reduction", locale))

        sep = "；" if locale != "en" else "; "
        desc = sep.join(reasons) if reasons else _t("mgmt_neutral", locale)
        return max(0, min(5, score)), desc

    @classmethod
    def score_growth_and_management(cls, annual_data: List[Dict],
                                    news_signals: Dict,
                                    locale: str = "zh") -> Tuple[int, List[str]]:
        """增长与管理层总分 (25 分)"""
        details = []
        total = 0
        pts = _t("pts", locale)

        profit_list = []
        for year_data in annual_data:
            try:
                np_raw = year_data.get("net_profit", "0")
                if isinstance(np_raw, str):
                    if "亿" in np_raw:
                        val = float(np_raw.replace("亿", "").strip()) * 10000
                    elif "万" in np_raw:
                        val = float(np_raw.replace("万", "").strip())
                    else:
                        val = float(np_raw.strip()) if np_raw.strip() else 0.0
                else:
                    val = float(np_raw)
                profit_list.append(val)
            except Exception:
                pass

        if profit_list:
            growth_score, growth_desc = cls.score_profit_growth(profit_list, locale=locale)
            details.append(f"{_t('growth_label', locale)}: {growth_score}/12 {pts} — {growth_desc}")
            total += growth_score

            consistency_score, consistency_desc = cls.score_profit_consistency(profit_list, locale)
            details.append(f"{_t('consist_label', locale)}: {consistency_score}/8 {pts} — {consistency_desc}")
            total += consistency_score
        else:
            total += 10
            details.append(f"{_t('profit_data_label', locale)}: 10/20 {pts} — {_t('data_missing', locale)}")

        mgmt_score, mgmt_desc = cls.score_management(news_signals, locale)
        details.append(f"{_t('mgmt_label', locale)}: {mgmt_score}/5 {pts} — {mgmt_desc}")
        total += mgmt_score

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第三维：财务安全性 (20 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_debt(debt_to_equity: float, locale: str = "zh") -> Tuple[int, str]:
        """负债风险评分 (10 分)"""
        if debt_to_equity < 0.3:
            return 10, _t("debt_very_low", locale)
        elif debt_to_equity < 0.5:
            return 8, _t("debt_low", locale)
        elif debt_to_equity < 0.8:
            return 6, _t("debt_moderate", locale)
        elif debt_to_equity < 1.0:
            return 4, _t("debt_elevated", locale)
        elif debt_to_equity < 2.0:
            return 2, _t("debt_high", locale)
        else:
            return -5, _t("debt_extreme", locale)

    @staticmethod
    def score_profitability_sustainability(profit_list: List[float], locale: str = "zh") -> Tuple[int, str]:
        """盈利可持续性评分 (10 分)"""
        if len(profit_list) < 3:
            return 5, _t("sust_data_short", locale)

        recent_3y = profit_list[:3]
        positive_count = sum(1 for p in recent_3y if p > 0)

        if positive_count == 3:
            return 10, _t("sust_strong", locale)
        elif positive_count == 2:
            return 6, _t("sust_fair", locale)
        elif positive_count == 1:
            return 2, _t("sust_weak", locale)
        else:
            return -5, _t("sust_bankruptcy", locale)

    @classmethod
    def score_safety(cls, annual_data: List[Dict], locale: str = "zh") -> Tuple[int, List[str]]:
        """财务安全性总分 (20 分)"""
        details = []
        total = 0
        pts = _t("pts", locale)

        if not annual_data:
            return 0, [_t("safety_data_insufficient", locale)]

        latest = annual_data[0]

        try:
            debt_ratio = _pct(latest.get("debt_ratio")) / 100
            debt_score, debt_desc = cls.score_debt(debt_ratio, locale)
            details.append(f"{_t('debt_label', locale)}: {debt_score}/10 {pts} — {debt_desc}")
            total += debt_score
        except Exception:
            total += 5
            details.append(f"{_t('debt_label', locale)}: 5/10 {pts} — {_t('data_missing', locale)}")

        profit_list = []
        for year_data in annual_data:
            try:
                np_raw = year_data.get("net_profit", "0")
                if isinstance(np_raw, str):
                    if "亿" in np_raw:
                        val = float(np_raw.replace("亿", "").strip()) * 10000
                    elif "万" in np_raw:
                        val = float(np_raw.replace("万", "").strip())
                    else:
                        val = float(np_raw.strip()) if np_raw.strip() else 0.0
                else:
                    val = float(np_raw)
                profit_list.append(val)
            except Exception:
                pass

        if profit_list:
            sust_score, sust_desc = cls.score_profitability_sustainability(profit_list, locale)
            details.append(f"{_t('sust_label', locale)}: {sust_score}/10 {pts} — {sust_desc}")
            total += sust_score
        else:
            total += 5
            details.append(f"{_t('sust_label', locale)}: 5/10 {pts} — {_t('data_missing', locale)}")

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第四维：估值 (15 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_pe_valuation(pe_percentile: Optional[int], locale: str = "zh") -> Tuple[int, str]:
        """PE 估值评分 (7 分)"""
        if pe_percentile is None:
            return 3, _t("pe_data_missing", locale)

        if pe_percentile <= 20:
            return 7, _t("pe_cheap", locale)
        elif pe_percentile <= 40:
            return 5, _t("pe_fairly_cheap", locale)
        elif pe_percentile <= 60:
            return 3, _t("pe_fair", locale)
        elif pe_percentile <= 80:
            return 1, _t("pe_fairly_expensive", locale)
        else:
            return -2, _t("pe_expensive", locale)

    @staticmethod
    def score_pb_valuation(pb_percentile: Optional[int], locale: str = "zh") -> Tuple[int, str]:
        """PB 估值评分 (5 分)"""
        if pb_percentile is None:
            return 2, _t("pb_data_missing", locale)

        if pb_percentile <= 20:
            return 5, _t("pb_cheap", locale)
        elif pb_percentile <= 40:
            return 4, _t("pb_fairly_cheap", locale)
        elif pb_percentile <= 60:
            return 2, _t("pb_fair", locale)
        elif pb_percentile <= 80:
            return 1, _t("pb_fairly_expensive", locale)
        else:
            return -1, _t("pb_expensive", locale)

    @staticmethod
    def score_price_position(price_52week_pct: Optional[float], locale: str = "zh") -> Tuple[int, str]:
        """52周价格位置评分 (3 分)"""
        if price_52week_pct is None:
            return 0, _t("pos_data_missing", locale)

        if price_52week_pct >= 90:
            return -3, _t("pos_near_high", locale)
        elif price_52week_pct >= 80:
            return -1, _t("pos_near_high_mild", locale)
        elif price_52week_pct <= 10:
            return 3, _t("pos_near_low", locale)
        elif price_52week_pct <= 20:
            return 2, _t("pos_near_low_mild", locale)
        else:
            return 1, _t("pos_mid", locale)

    @classmethod
    def score_valuation(cls, pe_percentile: Optional[int], pb_percentile: Optional[int],
                        price_52week_pct: Optional[float],
                        locale: str = "zh") -> Tuple[int, List[str]]:
        """估值总分 (15 分)"""
        details = []
        total = 0
        pts = _t("pts", locale)

        pe_score, pe_desc = cls.score_pe_valuation(pe_percentile, locale)
        details.append(f"{_t('pe_label', locale)}: {pe_score}/7 {pts} — {pe_desc}")
        total += pe_score

        pb_score, pb_desc = cls.score_pb_valuation(pb_percentile, locale)
        details.append(f"{_t('pb_label', locale)}: {pb_score}/5 {pts} — {pb_desc}")
        total += pb_score

        pos_score, pos_desc = cls.score_price_position(price_52week_pct, locale)
        details.append(f"{_t('pos_label', locale)}: {pos_score}/3 {pts} — {pos_desc}")
        total += pos_score

        return total, details

    # ─────────────────────────────────────────────────────────
    # 最终评级转换
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def get_grade_and_conclusion(score: int, locale: str = "zh") -> Dict:
        """根据综合得分生成评级（conclusion 始终为中文，用于 DB 存储）"""
        if score >= 85:
            return {"grade": "A",  "conclusion": "买入", "emoji": "🟢", "rating_desc": _t("grade_a_desc", locale)}
        elif score >= 75:
            return {"grade": "B+", "conclusion": "买入", "emoji": "🟢", "rating_desc": _t("grade_bplus_desc", locale)}
        elif score >= 65:
            return {"grade": "B",  "conclusion": "持有", "emoji": "🟡", "rating_desc": _t("grade_b_desc", locale)}
        elif score >= 55:
            return {"grade": "B-", "conclusion": "持有", "emoji": "🟡", "rating_desc": _t("grade_bminus_desc", locale)}
        elif score >= 45:
            return {"grade": "C+", "conclusion": "观察", "emoji": "🟠", "rating_desc": _t("grade_cplus_desc", locale)}
        elif score >= 35:
            return {"grade": "C",  "conclusion": "减持", "emoji": "🔴", "rating_desc": _t("grade_c_desc", locale)}
        else:
            return {"grade": "D",  "conclusion": "卖出", "emoji": "🔴", "rating_desc": _t("grade_d_desc", locale)}

    # ─────────────────────────────────────────────────────────
    # 红旗提取
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def extract_red_flags(annual_data: List[Dict], pe_pct: Optional[int],
                          price_52week_pct: Optional[float],
                          news_signals: Dict,
                          locale: str = "zh") -> List[str]:
        """提取所有红旗"""
        flags = []

        if not annual_data:
            return flags

        latest = annual_data[0]

        try:
            roe_pct = _pct(latest.get("roe"))
            if roe_pct < 5 and roe_pct >= 0:
                flags.append(_t("flag_roe_low", locale))
            elif roe_pct < 0:
                flags.append(_t("flag_roe_negative", locale))
        except Exception:
            pass

        try:
            margin_pct = _pct(latest.get("net_margin"))
            if margin_pct < 0:
                flags.append(_t("flag_margin_negative", locale))
        except Exception:
            pass

        try:
            debt_ratio = _pct(latest.get("debt_ratio")) / 100
            if debt_ratio > 2.0:
                flags.append(_t("flag_debt_extreme", locale))
        except Exception:
            pass

        if price_52week_pct is not None and price_52week_pct > 90:
            flags.append(_t("flag_price_high", locale).format(pct=price_52week_pct))

        profit_list = []
        for year_data in annual_data[:3]:
            try:
                np_raw = year_data.get("net_profit", "0")
                if isinstance(np_raw, str):
                    if "亿" in np_raw:
                        val = float(np_raw.replace("亿", "").strip()) * 10000
                    elif "万" in np_raw:
                        val = float(np_raw.replace("万", "").strip())
                    else:
                        val = float(np_raw.strip()) if np_raw.strip() else 0.0
                else:
                    val = float(np_raw)
                profit_list.append(val)
            except Exception:
                pass

        if len(profit_list) >= 3 and all(p < 0 for p in profit_list):
            flags.append(_t("flag_consecutive_loss", locale))

        if news_signals.get("high_neg_resignation", 0) > 0:
            flags.append(_t("flag_resignation", locale))

        if news_signals.get("fund_flow_ratio", 0) < -5:
            flags.append(_t("flag_fund_outflow", locale))

        return flags

    # ─────────────────────────────────────────────────────────
    # 主评级函数
    # ─────────────────────────────────────────────────────────

    # ════════════════════════════════════════════════════════════
    # US-116 类型感知评级：质量×价格两轴 + 招牌标尺 + 数据门
    # 判断依据出处（每条线不许拍脑袋）：
    #   ① 自己跟自己比：pe/pb 历史分位（已有）
    #   ③ 每类学术招牌标尺：
    #      mature_value → Piotroski F-score（9点制基本面趋势，治价值陷阱）
    #      growth/pre_profit → Rule of 40（营收增速%+利润率%≥40，不罚无利润）
    #      distressed → 生存检查（Altman Z-score 思路：亏损/负债/营收趋势）
    #      financial → CAMELS 简化（看 ROE/账面增长，不罚负债率=杠杆是业务）
    #   ② 跟同类比：Damodaran 行业分位 → Phase 2（industry_benchmarks 表）
    # 详见 PRODUCT.md US-116 / 研究方法论骨架
    # ════════════════════════════════════════════════════════════

    # type → 评分配方 key
    _PROFILE_OF = {
        "mature_value": "mature", "utility": "mature", "etf": "mature",
        "financial": "financial",
        "growth_tech": "growth", "supply_chain": "growth", "speculative": "growth",
        "pre_profit": "preprofit",
        "cyclical": "cyclical",
        "turnaround": "turnaround",
        "distressed": "distressed",
    }
    # profile → 质量组件(权重) + 价格用哪个分位 + 最少可算组件数（少于则 NR）
    _PROFILES = {
        # 成熟价值股：巴菲特质量 + Piotroski 趋势
        "mature":     {"q": [("roe", .30), ("margin", .20), ("stability", .20),
                             ("rev_cagr", .15), ("piotroski", .15)], "v": "pe", "min": 2},
        # 银行/金融：CAMELS 简化——看 ROE/盈利能力/账面增长，不看负债率（杠杆是业务）
        # margin 纳入配方，让只有 signals（无年报）的非A股银行也能评级而非 NR
        "financial":  {"q": [("roe", .40), ("margin", .20), ("stability", .20),
                             ("rev_cagr", .20)], "v": "pb", "min": 2},
        # 成长科技：Rule of 40——增速 + 烧钱效率，不罚当期低 ROE
        "growth":     {"q": [("rev_cagr", .35), ("rule40", .30), ("margin", .20),
                             ("stability", .15)], "v": "pe_or_price", "min": 2},
        # 未盈利成长：只看增速 + 烧钱效率，无利润是定义不是罪
        "preprofit":  {"q": [("rev_cagr", .55), ("rule40", .45)], "v": "price", "min": 1},
        # 周期股：质量=中周期盈利力 + 稳定度 + 能否扛过谷底（survival）；
        # 不放 piotroski/rev_cagr 这类趋势项——它们会在谷底误杀（而谷底正是该买的时候）。
        # 周期"时机"由估值轴的周期位置调整处理，与质量分离。
        "cyclical":   {"q": [("roe_mid", .30), ("margin_mid", .25), ("stability", .20),
                             ("survival", .25)], "v": "pb", "min": 2},
        # 困境反转：看恢复趋势（利润率/ROE 触底回升没）+ 生存 + PB 便宜不便宜
        "turnaround": {"q": [("recovery", .50), ("survival", .30), ("rev_cagr", .20)],
                       "v": "pb", "min": 1},
        # 困境/重整：真 Altman Z''（字段不全自动回退生存检查），不做估值打分
        "distressed": {"q": [("altman", 1.0)], "v": "none", "min": 1},
    }
    _TYPE_NAMES = {
        "mature_value": ("成熟价值股", "mature value"), "utility": ("公用事业", "utility"),
        "financial": ("银行/金融", "bank/financial"), "growth_tech": ("成长科技股", "growth/tech"),
        "supply_chain": ("供应链卡位股", "supply-chain"), "speculative": ("高风险题材股", "speculative"),
        "pre_profit": ("未盈利成长股", "pre-profit growth"), "cyclical": ("周期股", "cyclical"),
        "turnaround": ("困境反转股", "turnaround"),
        "distressed": ("困境/重整股", "distressed"), "etf": ("基金/ETF", "fund/ETF"),
    }

    _VALUE_TIERS = {"zh": ["便宜", "合理", "偏贵", "贵"],
                    "en": ["cheap", "fair", "pricey", "expensive"]}

    @staticmethod
    def _rz(zh: str, en: str, locale: str = "zh") -> str:
        return en if locale == "en" else zh

    @classmethod
    def _tier_label(cls, rank: int, locale: str) -> str:
        return cls._VALUE_TIERS["en" if locale == "en" else "zh"][rank]

    @staticmethod
    def _band(value: float, bands: list, default: int) -> int:
        """从高到低套档位：命中第一个 value >= 阈值的档，返回其分数；都不中返回 default。"""
        for thr, sc in bands:
            if value >= thr:
                return sc
        return default

    @staticmethod
    def _num(v):
        """解析财务值，处理 '%'、'亿'、'万' 单位；无法解析返回 None（区别于 0）。"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace("%", "")
        if not s:
            return None
        mult = 1.0
        if s.endswith("亿"):
            mult, s = 1e4, s[:-1]
        elif s.endswith("万"):
            mult, s = 1.0, s[:-1]
        try:
            return float(s) * mult
        except (ValueError, TypeError):
            return None

    @classmethod
    def _series(cls, annual, field):
        """newest-first 数值序列（annual[0] 为最新年）。"""
        return [cls._num(y.get(field)) for y in (annual or [])]

    # ── 质量组件，各返回 (0-100 或 None, 人话理由) ──────────────
    @classmethod
    def _q_roe(cls, annual, signals, locale, industry=None):
        roe = cls._num((annual[0] if annual else {}).get("roe"))
        if roe is None and signals and signals.get("roe") is not None:
            roe = signals["roe"] * 100
        if roe is None:
            return None, ""
        # ② 行业中性化：有行业 ROE 基准就跟同行比（z-score），否则绝对档（巴菲特线15%）
        z = cls._industry_z(roe, industry, "roe")
        if z is not None:
            sc = cls._band(z, [(1.5, 95), (0.5, 80), (-0.5, 60), (-1.5, 35)], 15)
            word = cls._rz("同行领先" if z >= 0.5 else ("同行相当" if z >= -0.5 else "低于同行"),
                           "top vs peers" if z >= 0.5 else ("in line" if z >= -0.5 else "below peers"), locale)
            return sc, cls._rz(f"ROE {roe:.1f}%，{word}（{z:+.1f}个标准差）",
                               f"ROE {roe:.1f}%, {word} ({z:+.1f}σ)", locale)
        sc = cls._band(roe, [(25, 100), (20, 90), (15, 78), (10, 60), (5, 40), (0, 20)], 0)
        return sc, cls._rz(f"ROE {roe:.1f}%（巴菲特线 15%）", f"ROE {roe:.1f}% (Buffett bar 15%)", locale)

    @classmethod
    def _q_margin(cls, annual, signals, locale, industry=None):
        m = cls._num((annual[0] if annual else {}).get("net_margin"))
        if m is None and signals and signals.get("profit_margin") is not None:
            m = signals["profit_margin"] * 100
        if m is None:
            return None, ""
        sc = cls._band(m, [(25, 100), (15, 80), (10, 60), (5, 40), (0, 20)], 0)
        return sc, cls._rz(f"净利率 {m:.1f}%", f"net margin {m:.1f}%", locale)

    @classmethod
    def _q_stability(cls, annual, signals, locale, industry=None):
        roes = [v for v in cls._series(annual, "roe") if v is not None][:5]
        if len(roes) < 2:
            return None, ""
        avg = sum(roes) / len(roes)
        if avg == 0:
            return 10, cls._rz("ROE 波动大", "ROE volatile", locale)
        cv = (sum((x - avg) ** 2 for x in roes) / len(roes)) ** 0.5 / abs(avg)
        bands = [(0.10, 100), (0.20, 80), (0.30, 55), (0.50, 30)]
        sc = 10
        for thr, v in bands:
            if cv < thr:
                sc = v
                break
        return sc, cls._rz(f"{len(roes)}年 ROE 稳定度", f"{len(roes)}-yr ROE stability", locale)

    @classmethod
    def _q_rev_cagr(cls, annual, signals, locale, industry=None):
        revs = [v for v in cls._series(annual, "revenue") if v is not None]
        if len(revs) < 2 or revs[-1] <= 0 or revs[0] <= 0:
            return None, ""
        cagr = ((revs[0] / revs[-1]) ** (1 / (len(revs) - 1)) - 1) * 100
        sc = cls._band(cagr, [(30, 100), (20, 85), (15, 70), (10, 55), (0, 35)], 10)
        return sc, cls._rz(f"营收 {len(revs)}年复合增速 {cagr:.0f}%",
                           f"revenue {len(revs)}-yr CAGR {cagr:.0f}%", locale)

    @classmethod
    def _q_rule40(cls, annual, signals, locale, industry=None):
        """Rule of 40：最近一年营收增速% + 净利率% ≥ 40。"""
        revs = [v for v in cls._series(annual, "revenue") if v is not None]
        m = cls._num((annual[0] if annual else {}).get("net_margin"))
        if len(revs) < 2 or revs[1] <= 0 or m is None:
            return None, ""
        yoy = (revs[0] / revs[1] - 1) * 100
        score40 = yoy + m
        sc = cls._band(score40, [(40, 100), (30, 75), (20, 50), (10, 30)], 10)
        return sc, cls._rz(f"Rule of 40：增速{yoy:.0f}%+利润率{m:.0f}%={score40:.0f}",
                           f"Rule of 40: growth{yoy:.0f}%+margin{m:.0f}%={score40:.0f}", locale)

    @classmethod
    def _q_piotroski(cls, annual, signals, locale, industry=None):
        """完整 Piotroski-9（US-116 #3）。字段齐全→真9项；缺字段→用能算的子集（ROA无总资产时用ROE代理）。"""
        if len(annual or []) < 2:
            return None, ""
        cur, prev = annual[0], annual[1]
        n = cls._num
        tests, passed = 0, 0

        def chk(cond):
            nonlocal tests, passed
            tests += 1
            if cond:
                passed += 1

        def roa(y):
            ni, ta = n(y.get("net_profit")), n(y.get("total_assets"))
            if ni is not None and ta and ta > 0:
                return ni / ta * 100
            return n(y.get("roe"))  # 代理：无总资产时用 ROE

        def curr_ratio(y):
            ca, cl = n(y.get("current_assets")), n(y.get("current_liabilities"))
            return ca / cl if ca is not None and cl and cl > 0 else None

        def asset_turn(y):
            rev, ta = n(y.get("revenue")), n(y.get("total_assets"))
            return rev / ta if rev is not None and ta and ta > 0 else None

        ra_c, ra_p = roa(cur), roa(prev)
        cfo, ni_c = n(cur.get("cfo")), n(cur.get("net_profit"))
        d_c, d_p = n(cur.get("debt_ratio")), n(prev.get("debt_ratio"))
        cr_c, cr_p = curr_ratio(cur), curr_ratio(prev)
        sh_c, sh_p = n(cur.get("shares")), n(prev.get("shares"))
        gm_c, gm_p = n(cur.get("gross_margin")), n(prev.get("gross_margin"))
        at_c, at_p = asset_turn(cur), asset_turn(prev)

        if ra_c is not None:                         chk(ra_c > 0)             # 1 ROA>0
        if cfo is not None:                          chk(cfo > 0)             # 2 CFO>0
        if ra_c is not None and ra_p is not None:    chk(ra_c > ra_p)         # 3 ΔROA↑
        if cfo is not None and ni_c is not None:     chk(cfo > ni_c)          # 4 CFO>净利(应计,关键)
        if d_c is not None and d_p is not None:      chk(d_c < d_p)           # 5 杠杆↓
        if cr_c is not None and cr_p is not None:    chk(cr_c > cr_p)         # 6 流动比率↑
        if sh_c is not None and sh_p and sh_p > 0:   chk(sh_c <= sh_p * 1.01) # 7 未增发
        if gm_c is not None and gm_p is not None:    chk(gm_c > gm_p)         # 8 毛利率↑
        if at_c is not None and at_p is not None:    chk(at_c > at_p)         # 9 资产周转↑

        if tests < 3:
            return None, ""
        sc = round(passed / tests * 100)
        tag = "9项" if tests >= 8 else cls._rz(f"{tests}项·数据有限", f"{tests} tests·limited data", locale)
        return sc, cls._rz(f"Piotroski {passed}/{tests} 项向好（{tag}）",
                           f"Piotroski {passed}/{tests} improving ({tag})", locale)

    @classmethod
    def _q_survival(cls, annual, signals, locale, industry=None):
        """困境股生存检查（Altman Z 思路：亏损/负债/营收趋势）。"""
        if not annual:
            return None, ""
        sc = 100
        notes = []
        profits = [v for v in cls._series(annual, "net_profit")[:3] if v is not None]
        loss_years = sum(1 for p in profits if p < 0)
        if loss_years:
            sc -= 25 * loss_years
            notes.append(cls._rz(f"近{len(profits)}年亏{loss_years}年", f"{loss_years} loss yrs", locale))
        d = cls._num(annual[0].get("debt_ratio"))
        if d is not None and d > 80:
            sc -= 25
            notes.append(cls._rz(f"负债率{d:.0f}%偏高", f"debt {d:.0f}%", locale))
        revs = [v for v in cls._series(annual, "revenue") if v is not None]
        if len(revs) >= 2 and revs[0] < revs[1]:
            sc -= 15
            notes.append(cls._rz("营收下滑", "revenue falling", locale))
        sc = max(0, sc)
        return sc, cls._rz("生存检查：" + ("、".join(notes) if notes else "暂稳"),
                           "Survival: " + ("; ".join(notes) if notes else "stable"), locale)

    @classmethod
    def _q_altman(cls, annual, signals, locale, industry=None):
        """真 Altman Z''（新兴市场四变量版，用账面权益）。字段不全 → 回退 _q_survival。
        Z'' = 3.25 + 6.56·(营运资本/资产) + 3.26·(留存/资产) + 6.72·(EBIT/资产) + 1.05·(权益/总负债)
        >2.6 安全 / 1.1–2.6 灰区 / <1.1 危险。"""
        if not annual:
            return cls._q_survival(annual, signals, locale)
        y, n = annual[0], cls._num
        ta = n(y.get("total_assets"))
        ca, cl = n(y.get("current_assets")), n(y.get("current_liabilities"))
        re, ebit, eq = n(y.get("retained_earnings")), n(y.get("ebit")), n(y.get("equity"))
        if not (ta and ta > 0 and ca is not None and cl is not None
                and re is not None and ebit is not None and eq is not None):
            return cls._q_survival(annual, signals, locale)  # 数据不全 → 回退
        tl = ta - eq
        if tl <= 0:
            tl = ta * 0.01  # 几乎无负债，防除零
        z = 3.25 + 6.56 * ((ca - cl) / ta) + 3.26 * (re / ta) + 6.72 * (ebit / ta) + 1.05 * (eq / tl)
        if z >= 2.6:
            sc, zone = min(100, 80 + (z - 2.6) * 10), cls._rz("安全区", "safe", locale)
        elif z >= 1.1:
            sc, zone = 30 + (z - 1.1) / 1.5 * 40, cls._rz("灰色地带", "grey zone", locale)
        else:
            sc, zone = max(0, z / 1.1 * 30), cls._rz("危险区", "distress zone", locale)
        return round(sc), cls._rz(f"Altman Z''={z:.2f}（{zone}，>2.6安全/<1.1危险）",
                                  f"Altman Z''={z:.2f} ({zone})", locale)

    @classmethod
    def _q_recovery(cls, annual, signals, locale, industry=None):
        """困境反转：利润率/ROE 是否触底回升（趋势向上=好，不看当期绝对值）。"""
        roes = [v for v in cls._series(annual, "roe") if v is not None]
        margins = [v for v in cls._series(annual, "net_margin") if v is not None]
        if len(roes) < 2 and len(margins) < 2:
            return None, ""
        sc, notes = 40, []
        # ROE 改善（newest-first：roes[0] 最新）
        if len(roes) >= 2:
            if roes[0] > roes[1]:
                sc += 25
                notes.append(cls._rz("ROE 回升", "ROE recovering", locale))
                if len(roes) >= 3 and roes[1] > roes[2]:
                    sc += 15  # 连续两年改善
                if roes[0] > 0 and roes[1] <= 0:
                    sc += 20  # 扭亏为盈
                    notes.append(cls._rz("扭亏为盈", "back to profit", locale))
            else:
                sc -= 20
                notes.append(cls._rz("ROE 仍在恶化", "ROE still worsening", locale))
        if len(margins) >= 2:
            if margins[0] > margins[1]:
                sc += 15
                notes.append(cls._rz("利润率改善", "margin improving", locale))
            else:
                sc -= 10
        sc = max(0, min(100, sc))
        return sc, cls._rz("恢复趋势：" + ("、".join(notes) if notes else "暂不明显"),
                           "Recovery: " + ("; ".join(notes) if notes else "unclear"), locale)

    @classmethod
    def _q_roe_mid(cls, annual, signals, locale, industry=None):
        """周期股：用中周期（历史均值）ROE，峰值不虚高、谷底不误杀。"""
        roes = [v for v in cls._series(annual, "roe") if v is not None]
        if not roes:
            return cls._q_roe(annual, signals, locale)
        avg = sum(roes) / len(roes)
        sc = cls._band(avg, [(25, 100), (20, 90), (15, 78), (10, 60), (5, 40), (0, 20)], 0)
        return sc, cls._rz(f"中周期 ROE {avg:.1f}%（{len(roes)}年均）",
                           f"mid-cycle ROE {avg:.1f}% ({len(roes)}y avg)", locale)

    @classmethod
    def _q_margin_mid(cls, annual, signals, locale, industry=None):
        """周期股：用中周期（历史均值）净利率。"""
        ms = [v for v in cls._series(annual, "net_margin") if v is not None]
        if not ms:
            return cls._q_margin(annual, signals, locale)
        avg = sum(ms) / len(ms)
        sc = cls._band(avg, [(25, 100), (15, 80), (10, 60), (5, 40), (0, 20)], 0)
        return sc, cls._rz(f"中周期净利率 {avg:.1f}%（{len(ms)}年均）",
                           f"mid-cycle margin {avg:.1f}% ({len(ms)}y avg)", locale)

    @classmethod
    def _cycle_position(cls, annual, locale):
        """周期位置：当前 margin ÷ 中周期 margin。返回 (人话, ratio, 估值档调整 ±1)。
        研究锚定（Industrials IB）：谷底通常比中周期低 30-50% → 0.70 / 1.30 阈值。"""
        ms = [v for v in cls._series(annual, "net_margin") if v is not None]
        if len(ms) < 3:
            return None, None, 0
        mid = sum(ms) / len(ms)
        cur = ms[0]
        if mid <= 0 or cur < 0:  # 中周期非正 或 当前亏损 → 无法判断周期位置
            return None, None, 0
        ratio = cur / mid
        n = len(ms)
        inc = "" if n >= 7 else cls._rz(f"（基于{n}年，周期可能不完整）",
                                        f" (based on {n}y, cycle may be incomplete)", locale)
        if ratio > 1.30:
            return (cls._rz(f"利润率在周期高位（当前是中周期的{ratio*100:.0f}%），PE看着便宜其实贵{inc}",
                            f"margin near cycle peak ({ratio*100:.0f}% of mid-cycle) — low PE is a trap{inc}",
                            locale), ratio, +1)
        if ratio < 0.70:
            return (cls._rz(f"利润率在周期低谷（当前是中周期的{ratio*100:.0f}%），可能是机会{inc}",
                            f"margin near cycle trough ({ratio*100:.0f}% of mid-cycle) — possible opportunity{inc}",
                            locale), ratio, -1)
        return (cls._rz(f"利润率在周期中段{inc}", f"margin mid-cycle{inc}", locale), ratio, 0)

    @classmethod
    def _compute_quality(cls, profile, annual, signals, locale, industry=None):
        """按配方算质量分 (0-100)；可算组件不足 → None（触发 NR）。"""
        fns = {"roe": cls._q_roe, "margin": cls._q_margin, "stability": cls._q_stability,
               "rev_cagr": cls._q_rev_cagr, "rule40": cls._q_rule40,
               "piotroski": cls._q_piotroski, "survival": cls._q_survival,
               "recovery": cls._q_recovery, "altman": cls._q_altman,
               "roe_mid": cls._q_roe_mid, "margin_mid": cls._q_margin_mid}
        got, reasons = [], []
        for key, w in profile["q"]:
            val, reason = fns[key](annual, signals, locale, industry)
            if val is not None:
                got.append((val, w))
                reasons.append((w, reason))
        if len(got) < profile["min"]:
            return None, []
        quality = sum(v * w for v, w in got) / sum(w for _, w in got)
        reasons.sort(reverse=True)
        return quality, [r for _, r in reasons if r]

    @classmethod
    def _forensic_flags(cls, annual, locale):
        """步2种子：现金流 vs 利润背离（最强单一打假信号）。"""
        flags, penalty = [], 0
        if annual:
            ocf = cls._num(annual[0].get("ocf_per_share"))
            eps = cls._num(annual[0].get("eps"))
            np_ = cls._num(annual[0].get("net_profit"))
            if ocf is not None and eps is not None and eps > 0:
                if ocf / eps < 0.8:
                    penalty += 15
                    flags.append(cls._rz(
                        f"利润是正的，但经营现金流只有利润的{ocf/eps*100:.0f}%——赚的钱没真正进账户",
                        f"Profit positive but OCF only {ocf/eps*100:.0f}% of it — earnings not turning to cash",
                        locale))
            elif np_ is not None and np_ > 0 and ocf is not None and ocf < 0:
                penalty += 20
                flags.append(cls._rz("账面盈利，但经营现金流为负——利润质量存疑",
                                     "Book profit but negative operating cash flow", locale))
        return flags, penalty

    @staticmethod
    def _industry_z(value, industry, metric):
        """个股某估值指标 vs 同行业的 z-score（US-116 v2 行业中性化）。无基准→None。"""
        if value is None or not industry:
            return None
        try:
            import db
            b = db.get_industry_benchmark(industry, metric)
        except Exception:
            return None
        if not b or not b.get("std") or b["std"] <= 0:
            return None
        return (float(value) - b["mean"]) / b["std"]

    @classmethod
    def _value_tier(cls, profile, pe_pct, pb_pct, price_52week_pct, locale,
                    pe_current=None, pb_current=None, industry=None):
        """估值档：返回 (tier_zh, rank0-3, 理由)；无数据 → (None, 1, '')。
        优先级：① 跟同行业比(行业中性化 z) > ② 跟自己历史比(分位) > ③ 股价位置。"""
        metric = profile["v"]
        if metric == "none":
            return None, 1, ""

        # ① 行业中性化 z-score（v2）——A股有行业基准时优先
        z_metric = "pb" if metric == "pb" else "pe"
        z_val = pb_current if z_metric == "pb" else pe_current
        z = cls._industry_z(z_val, industry, z_metric)
        if z is not None:
            name = "PB" if z_metric == "pb" else "PE"
            if z <= -1.0:
                rank, word = 0, cls._rz("低于同行", "below peers", locale)
            elif z <= 0.5:
                rank, word = 1, cls._rz("与同行相当", "in line with peers", locale)
            elif z <= 1.5:
                rank, word = 2, cls._rz("高于同行", "above peers", locale)
            else:
                rank, word = 3, cls._rz("远高于同行", "well above peers", locale)
            reason = cls._rz(f"{name} {word}（{z:+.1f}个标准差）",
                             f"{name} {word} ({z:+.1f}σ vs industry)", locale)
            return cls._tier_label(rank, locale), rank, reason

        def from_pct(p, name):
            if p is None:
                return None
            if p <= 25:
                return 0, cls._rz(f"{name}处于历史低位（第{p}百分位）", f"{name} historically cheap (pct {p})", locale)
            if p <= 60:
                return 1, cls._rz(f"{name}估值合理（第{p}百分位）", f"{name} fair (pct {p})", locale)
            if p <= 80:
                return 2, cls._rz(f"{name}偏贵（第{p}百分位）", f"{name} pricey (pct {p})", locale)
            return 3, cls._rz(f"{name}处于历史高位（第{p}百分位）", f"{name} historically expensive (pct {p})", locale)

        res = None
        if metric == "pb":
            res = from_pct(pb_pct, "PB")
        elif metric == "pe":
            res = from_pct(pe_pct, "PE")
        elif metric == "pe_or_price":
            res = from_pct(pe_pct, "PE")
        if res is None and metric in ("price", "pe_or_price") and price_52week_pct is not None:
            p = price_52week_pct
            if p >= 85:
                res = (3, cls._rz(f"股价接近52周高点（{p:.0f}%位置）", f"near 52-wk high ({p:.0f}%)", locale))
            elif p >= 65:
                res = (2, cls._rz(f"股价处于偏高位置（{p:.0f}%）", f"upper range ({p:.0f}%)", locale))
            elif p >= 35:
                res = (1, cls._rz(f"股价处于中位（{p:.0f}%）", f"mid range ({p:.0f}%)", locale))
            else:
                res = (0, cls._rz(f"股价处于偏低位置（{p:.0f}%）", f"lower range ({p:.0f}%)", locale))
        if res is None:
            return None, 1, ""
        rank, reason = res
        return cls._tier_label(rank, locale), rank, reason

    # 质量档 × 估值档 → (grade, conclusion, emoji, (一句话_zh, _en))  —— 方案 A 矩阵
    _MATRIX = {
        ("hi", 0): ("A", "买入", "🟢", ("好公司 + 便宜，难得", "great business + cheap — rare")),
        ("hi", 1): ("B+", "买入", "🟢", ("好公司，价格合理", "great business, fair price")),
        ("hi", 2): ("B", "持有", "🟡", ("好公司，但价格不便宜", "great business, not cheap")),
        ("hi", 3): ("B-", "观察", "🟡", ("好公司，但贵了，等回调", "great business but expensive — wait")),
        ("mid", 0): ("B", "持有", "🟡", ("普通公司，胜在便宜", "average business, cheap")),
        ("mid", 1): ("B-", "持有", "🟡", ("普通公司，普通价", "average business, average price")),
        ("mid", 2): ("C+", "观察", "🟠", ("普通公司，偏贵", "average business, pricey")),
        ("mid", 3): ("C", "减持", "🔴", ("普通公司，太贵", "average business, too expensive")),
        ("lo", 0): ("C", "观察", "🟠", ("便宜有便宜的道理，警惕价值陷阱", "cheap for a reason — value trap risk")),
        ("lo", 1): ("C", "减持", "🔴", ("质量偏弱", "weak quality")),
        ("lo", 2): ("D", "减持", "🔴", ("质量弱又不便宜", "weak and not cheap")),
        ("lo", 3): ("D", "卖出", "🔴", ("又弱又贵", "weak and expensive")),
    }

    @classmethod
    def _combine(cls, quality, value_rank, has_value, profile, locale):
        band = "hi" if quality >= 65 else ("mid" if quality >= 40 else "lo")
        if profile["v"] == "none":
            # 困境股：质量=生存分，无估值轴
            if quality >= 55:
                return "C", "观察", "🟠", cls._rz("能撑住，先观察", "surviving, watch", locale)
            if quality >= 30:
                return "C", "减持", "🔴", cls._rz("生存承压，控制仓位", "under stress, trim", locale)
            return "D", "卖出", "🔴", cls._rz("生存堪忧", "survival at risk", locale)
        rank = value_rank if has_value else 1  # 无估值数据时按"合理"中性处理
        g, c, e, desc_pair = cls._MATRIX[(band, rank)]
        desc = cls._rz(desc_pair[0], desc_pair[1], locale)
        # 诚实原则：不知道价格就不喊"买入"，降为"持有"
        if not has_value and c == "买入":
            c = "持有"
            desc = cls._rz(desc + "（价格数据不足，先不下买入结论）",
                           desc + " (price data thin — holding off on a buy call)", locale)
        return g, c, e, desc

    @classmethod
    def rate_stock(cls, code: str, name: str, annual_data: List[Dict],
                   pe_percentile: Optional[int], pb_percentile: Optional[int],
                   price_52week_pct: Optional[float],
                   news_signals: Dict,
                   locale: str = "zh",
                   signals: Dict = None,
                   company_type: Optional[str] = None,
                   pe_current: Optional[float] = None,
                   pb_current: Optional[float] = None,
                   industry: Optional[str] = None) -> Dict:
        """
        类型感知评级（US-116）。质量×价格两轴，按 company_type 选尺子。
        无 company_type → 回退旧版通用评级（向后兼容）。
        pe_current/pb_current/industry：用于 v2 行业中性化估值（有则优先）。
        """
        if not company_type:
            return cls._rate_legacy(code, name, annual_data, pe_percentile,
                                    pb_percentile, price_52week_pct, news_signals,
                                    locale, signals)

        profile_key = cls._PROFILE_OF.get(company_type, "mature")
        profile = cls._PROFILES[profile_key]
        type_zh, type_en = cls._TYPE_NAMES.get(company_type, ("公司", "company"))
        type_label = cls._rz(type_zh, type_en, locale)

        # 数据门：质量无法计算 → NR「数据不足，暂不评级」，绝不返回 D
        quality, q_reasons = cls._compute_quality(profile, annual_data, signals, locale, industry)
        if quality is None:
            return {
                "code": code, "name": name, "score": None,
                "grade": "NR", "conclusion": cls._rz("数据不足，暂不评级", "Not rated — insufficient data", locale),
                "emoji": "⚪",
                "quality_score": None, "value_tier": None,
                "components": {"quality": (None, []), "value": (None, ""),
                               "type": company_type, "profile": profile_key},
                "red_flags": [], "data_incomplete": 1,
                "reasoning": cls._rz(
                    f"按{type_label}的标准看，但当前缺少足够财务数据，暂不给评级（不是看空，是没数据）。",
                    f"Judged as {type_label}, but not enough financial data yet — not rated (no view, not bearish).",
                    locale),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        # 打假叠加层（步2种子）：现金流 vs 利润背离 → 扣质量分
        flags, penalty = cls._forensic_flags(annual_data, locale)
        quality = max(0.0, min(100.0, quality - penalty))

        tier, value_rank, v_reason = cls._value_tier(
            profile, pe_percentile, pb_percentile, price_52week_pct, locale,
            pe_current=pe_current, pb_current=pb_current, industry=industry)
        has_value = tier is not None

        # 周期股：按周期位置调整估值档（峰值往贵推=PE陷阱预警，谷底往便宜推=机会）
        cycle_note = ""
        if profile_key == "cyclical":
            cycle_note, _ratio, _delta = cls._cycle_position(annual_data, locale)
            if has_value and _delta:
                value_rank = max(0, min(3, value_rank + _delta))
                tier = cls._tier_label(value_rank, locale)

        grade, conclusion, emoji, verdict = cls._combine(
            quality, value_rank, has_value, profile, locale)

        q_int = round(quality)
        top_q = q_reasons[0] if q_reasons else ""
        reasoning = cls._rz(
            f"按{type_label}的标准看：质量 {q_int}/100（{top_q}），"
            f"{('估值' + tier) if has_value else '估值数据不足'}。{verdict}。",
            f"As {type_label}: quality {q_int}/100 ({top_q}), "
            f"{('valuation ' + (tier or '')) if has_value else 'valuation data thin'}. {verdict}.",
            locale)
        if cycle_note:
            reasoning += "\n🔄 " + cycle_note
        if flags:
            reasoning += "\n⚠ " + flags[0]

        return {
            "code": code, "name": name,
            "score": q_int,            # quant_score 列存质量分
            "grade": grade, "conclusion": conclusion, "emoji": emoji,
            "quality_score": q_int, "value_tier": tier,
            "components": {
                "quality": (q_int, q_reasons),
                "value": (tier, v_reason),
                "type": company_type, "profile": profile_key,
            },
            "red_flags": flags,
            "reasoning": reasoning,
            "data_incomplete": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    @classmethod
    def _rate_legacy(cls, code: str, name: str, annual_data: List[Dict],
                     pe_percentile: Optional[int], pb_percentile: Optional[int],
                     price_52week_pct: Optional[float],
                     news_signals: Dict,
                     locale: str = "zh",
                     signals: Dict = None) -> Dict:
        """旧版通用评级（无 company_type 时回退）。"""
        # 数据完整度检测：关键字段有多少是实际有值的（只把 None/空字符串视为缺失，0 是合法值）
        _key_fields = ["roe", "net_margin", "debt_ratio", "net_profit"]
        _present = sum(
            1 for f in _key_fields
            if annual_data and annual_data[0].get(f) not in (None, "")
        )
        data_incomplete = int(_present < 2)  # 4个关键字段中少于2个有值 → 数据不完整

        moat_score, moat_details = cls.score_moat(annual_data, locale, signals=signals)
        growth_score, growth_details = cls.score_growth_and_management(annual_data, news_signals, locale)
        safety_score, safety_details = cls.score_safety(annual_data, locale)
        valuation_score, valuation_details = cls.score_valuation(
            pe_percentile, pb_percentile, price_52week_pct, locale
        )

        total_score = moat_score + growth_score + safety_score + valuation_score
        grade_info = cls.get_grade_and_conclusion(total_score, locale)
        red_flags = cls.extract_red_flags(annual_data, pe_percentile, price_52week_pct, news_signals, locale)

        reasoning = _t("reasoning_template", locale).format(score=total_score, desc=grade_info["rating_desc"])
        if red_flags:
            reasoning += "\n" + _t("reasoning_risk", locale).format(flag=red_flags[0])

        return {
            "code": code,
            "name": name,
            "score": total_score,
            "grade": grade_info["grade"],
            "conclusion": grade_info["conclusion"],
            "emoji": grade_info["emoji"],
            "components": {
                "moat": (moat_score, moat_details),
                "growth_management": (growth_score, growth_details),
                "safety": (safety_score, safety_details),
                "valuation": (valuation_score, valuation_details),
            },
            "red_flags": red_flags,
            "reasoning": reasoning,
            "data_incomplete": data_incomplete,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


# ─────────────────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    annual_data_demo = [
        {"year": "2025", "roe": "19.70%", "net_margin": "9.75%", "debt_ratio": "61.17%",
         "net_profit": "439.45亿", "eps": "5.8000", "ocf_per_share": "7.02", "bvps": "29.38"},
        {"year": "2024", "roe": "21.29%", "net_margin": "9.52%", "debt_ratio": "62.33%",
         "net_profit": "385.37亿", "eps": "5.4400", "ocf_per_share": "7.90", "bvps": "28.31"},
        {"year": "2023", "roe": "22.23%", "net_margin": "9.07%", "debt_ratio": "64.14%",
         "net_profit": "337.20亿", "eps": "4.9300", "ocf_per_share": "8.24", "bvps": "23.18"},
    ]

    for loc in ("zh", "en"):
        result = QuantitativeRater().rate_stock(
            code="000333", name="中国平安",
            annual_data=annual_data_demo,
            pe_percentile=65, pb_percentile=55, price_52week_pct=72,
            news_signals={"high_pos_buyback": 1},
            locale=loc,
        )

        print(f"\n{'='*60}  [{loc}]")
        print(f"{result['name']}  {result['score']}/100 → {result['emoji']} {result['grade']}")
        max_scores = {"moat": 40, "growth_management": 25, "safety": 20, "valuation": 15}
        for dim, (score, details) in result["components"].items():
            print(f"\n  {dim.upper()}: {score}/{max_scores.get(dim, 100)}")
            for d in details:
                print(f"    {d}")
        print(f"\n  {result['reasoning']}")
