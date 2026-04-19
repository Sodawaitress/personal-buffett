"""
私人巴菲特 · 基金/ETF 专用评分引擎 v1

5 种子类型：
  BROAD_ETF    宽基 ETF（沪深300、中证500 等）
  SECTOR_ETF   行业/主题 ETF
  BROAD_OEF    场外宽基指数基金（联接 A/C）
  ACTIVE_OEF   主动管理基金
  BOND_FUND    债券基金
  MONEY_FUND   货币基金

评分维度（满分 100）：
  产品质量  35 分  费率 + 规模 + 历史
  标的质量  35 分  指数类型 + 估值分位（可选）
  组合适配  20 分  持仓重复度 + 分散化贡献
  交易执行  10 分  适合定投 + 溢折价（ETF）

结论语言（不沿用股票的 买入/卖出）：
  适合定投  /  适合一次性配置  /  估值偏高，等一等
  主题过窄，谨慎  /  稳健配置  /  现金管理  /  谨慎
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ── 基金子类型 ───────────────────────────────────────────
class FundSubtype(str, Enum):
    BROAD_ETF  = "宽基ETF"
    SECTOR_ETF = "行业ETF"
    BROAD_OEF  = "场外宽基"
    ACTIVE_OEF = "主动基金"
    BOND_FUND  = "债券基金"
    MONEY_FUND = "货币基金"

# 各子类型中文说明
SUBTYPE_LABEL = {
    FundSubtype.BROAD_ETF:  "宽基指数ETF",
    FundSubtype.SECTOR_ETF: "行业/主题ETF",
    FundSubtype.BROAD_OEF:  "场外指数基金",
    FundSubtype.ACTIVE_OEF: "主动管理基金",
    FundSubtype.BOND_FUND:  "债券基金",
    FundSubtype.MONEY_FUND: "货币基金",
}

_BROAD_KEYWORDS = [
    "沪深300", "上证50", "中证500", "中证1000", "创业板",
    "科创50", "全A", "上证180", "深证100", "中证800",
    "中证全指", "A500", "上证指数", "深证成指",
]
_BROAD_KEYWORDS_EN = [
    "Total World", "Total Market", "All World", "Global", "World Index",
    "S&P 500", "SP500", "MSCI World", "MSCI ACWI", "Developed Markets",
    "Emerging Markets",
]
_BOND_KEYWORDS  = ["债", "债券", "利率", "信用", "纯债", "可转债", "转债"]
_MONEY_KEYWORDS = ["货币", "现金", "理财"]

def classify_fund(name: str, fund_type_str: str = "") -> FundSubtype:
    """根据名称和基金类型字符串判断子类型。"""
    n = name.upper()
    ft = fund_type_str.upper()

    if any(k in name for k in _MONEY_KEYWORDS):
        return FundSubtype.MONEY_FUND
    if any(k in name for k in _BOND_KEYWORDS) and "ETF" not in n:
        return FundSubtype.BOND_FUND
    if "债" in ft or "货币" in ft:
        return FundSubtype.BOND_FUND if "债" in ft else FundSubtype.MONEY_FUND

    is_etf_name = "ETF" in n or "LOF" in n
    is_linked   = "联接" in name or "指数" in name
    is_broad    = any(k in name for k in _BROAD_KEYWORDS) or any(k in name for k in _BROAD_KEYWORDS_EN)

    if is_etf_name:
        return FundSubtype.BROAD_ETF if is_broad else FundSubtype.SECTOR_ETF
    if is_linked or "指数" in ft:
        return FundSubtype.BROAD_OEF if is_broad else FundSubtype.SECTOR_ETF
    # 英文宽基基金（如 Smart Total World Hedged）
    if is_broad:
        return FundSubtype.BROAD_OEF
    return FundSubtype.ACTIVE_OEF


# ── 基金数据容器 ─────────────────────────────────────────
@dataclass
class FundData:
    code:           str
    name:           str
    subtype:        FundSubtype
    # 产品质量
    fee_rate:       Optional[float] = None   # 管理费率 %/年，如 0.5
    aum_bn:         Optional[float] = None   # 规模，亿元
    years_since_inception: Optional[float] = None  # 成立年数
    tracking_error: Optional[float] = None   # 跟踪误差 %
    # 标的质量
    pe_percentile:  Optional[int]   = None   # 所跟踪指数 PE 历史分位 0-100
    top10_pct:      Optional[float] = None   # 前10大持仓占比 %
    # 交易执行
    premium_pct:    Optional[float] = None   # 溢价率 % (ETF)
    # 持仓重复（用代码列表传入，不在这里计算）
    existing_cn_codes: List[str] = field(default_factory=list)
    # 原始行情（用于展示）
    nav:            Optional[float] = None
    change_pct:     Optional[float] = None


# ── 评分子函数 ───────────────────────────────────────────

def _score_fee(fee: Optional[float], subtype: FundSubtype) -> tuple[int, str]:
    if fee is None:
        return 8, "费率未知，按市场均值估计"
    if subtype in (FundSubtype.MONEY_FUND, FundSubtype.BOND_FUND):
        return 15, f"费率 {fee:.2f}%（货/债基正常水平）"
    if fee <= 0.15:
        return 15, f"费率 {fee:.2f}%，极低，对长期收益友好"
    if fee <= 0.5:
        return 12, f"费率 {fee:.2f}%，主流指数基金水平"
    if fee <= 1.0:
        return 8,  f"费率 {fee:.2f}%，偏高，留意长期摩擦"
    if fee <= 1.5:
        return 5,  f"费率 {fee:.2f}%，较高，主动基金常见"
    return 3, f"费率 {fee:.2f}%，很高，需用业绩弥补"

def _score_aum(aum: Optional[float], subtype: FundSubtype) -> tuple[int, str]:
    if aum is None:
        return 5, "规模未知"
    if subtype == FundSubtype.MONEY_FUND:
        return 10, f"规模 {aum:.1f} 亿"
    if aum >= 100:
        return 10, f"规模 {aum:.0f} 亿，旗舰级，流动性充裕"
    if aum >= 50:
        return 8,  f"规模 {aum:.0f} 亿，优质"
    if aum >= 10:
        return 6,  f"规模 {aum:.0f} 亿，中等"
    if aum >= 5:
        return 4,  f"规模 {aum:.0f} 亿，偏小"
    if aum >= 1:
        return 2,  f"规模 {aum:.1f} 亿，较小，留意清盘风险"
    return 0, f"规模 {aum:.2f} 亿，极小，清盘风险较高"

def _score_history(years: Optional[float]) -> tuple[int, str]:
    if years is None:
        return 3, "成立时间未知"
    if years >= 10:
        return 5, f"成立 {years:.0f} 年，历经多轮市场周期"
    if years >= 5:
        return 5, f"成立 {years:.1f} 年，历史记录充分"
    if years >= 3:
        return 4, f"成立 {years:.1f} 年，基本可参考"
    if years >= 1:
        return 3, f"成立 {years:.1f} 年，历史尚短"
    return 1, f"成立不足 1 年，暂无业绩参考"

def _score_tracking_error(te: Optional[float], subtype: FundSubtype) -> tuple[int, str]:
    if subtype in (FundSubtype.ACTIVE_OEF, FundSubtype.BOND_FUND, FundSubtype.MONEY_FUND):
        return 5, "主动/债基不考察跟踪误差"
    if te is None:
        return 3, "跟踪误差未知"
    if te <= 0.1:
        return 5, f"跟踪误差 {te:.2f}%，优秀"
    if te <= 0.2:
        return 4, f"跟踪误差 {te:.2f}%，良好"
    if te <= 0.5:
        return 3, f"跟踪误差 {te:.2f}%，尚可"
    return 1, f"跟踪误差 {te:.2f}%，偏高，复制效果不佳"

def _score_index_type(subtype: FundSubtype, name: str) -> tuple[int, str]:
    if subtype in (FundSubtype.BOND_FUND, FundSubtype.MONEY_FUND):
        return 25, "固收/货基：稳定性优先，不考察指数类型"
    if subtype == FundSubtype.ACTIVE_OEF:
        return 15, "主动基金：标的质量取决于基金经理选股能力"
    if subtype in (FundSubtype.BROAD_ETF, FundSubtype.BROAD_OEF):
        return 25, f"宽基指数：{name[:20]}，风险分散，长期表现稳健"
    # 行业 ETF / 场外行业
    high_risk = any(k in name for k in ["军工", "芯片", "半导体", "游戏", "区块链", "元宇宙"])
    if high_risk:
        return 12, f"主题/高波动行业：{name[:20]}，集中度高，波动大"
    stable = any(k in name for k in ["银行", "消费", "医药", "红利", "央企"])
    if stable:
        return 20, f"行业指数：{name[:20]}，细分赛道明确"
    return 17, f"行业指数：{name[:20]}"

def _score_valuation(pe_pct: Optional[int], subtype: FundSubtype) -> tuple[int, str]:
    if subtype in (FundSubtype.BOND_FUND, FundSubtype.MONEY_FUND):
        return 10, "固收/货基不适用股票估值分位"
    if pe_pct is None:
        return 10, "指数估值分位未知，按中性处理"
    if pe_pct <= 20:
        return 10, f"指数估值历史低位（{pe_pct}%分位），当前性价比高"
    if pe_pct <= 40:
        return 8,  f"指数估值合理偏低（{pe_pct}%分位）"
    if pe_pct <= 60:
        return 6,  f"指数估值中性（{pe_pct}%分位）"
    if pe_pct <= 80:
        return 3,  f"指数估值偏高（{pe_pct}%分位），谨慎入场"
    return 1, f"指数估值历史高位（{pe_pct}%分位），建议等待"

def _score_portfolio_fit(subtype: FundSubtype, existing: List[str], code: str) -> tuple[int, str]:
    if subtype in (FundSubtype.MONEY_FUND,):
        return 20, "货基作为流动性储备，与股票仓位不冲突"
    if subtype == FundSubtype.BOND_FUND:
        return 18, "债基有助于平衡组合波动，适合作为稳定仓"
    has_cn_stocks = len(existing) > 0
    if subtype in (FundSubtype.BROAD_ETF, FundSubtype.BROAD_OEF):
        if len(existing) >= 5:
            return 14, "已有多只个股，宽基指数可作为核心仓底仓，分散个股风险"
        return 20, "宽基指数适合作为核心仓，提供充分分散化"
    if subtype == FundSubtype.SECTOR_ETF:
        if has_cn_stocks:
            return 10, "已有个股持仓，行业 ETF 可能造成板块重叠，留意集中度"
        return 14, "行业 ETF 可作为专项配置，非核心仓"
    return 12, "主动基金组合适配取决于持仓风格"

def _score_execution(
    subtype: FundSubtype, premium: Optional[float]
) -> tuple[int, str]:
    if subtype in (FundSubtype.MONEY_FUND, FundSubtype.BOND_FUND):
        return 10, "货/债基支持 T+0 或 T+1 赎回，流动性充裕"
    sip_score = 5  # 定投基础分
    if subtype in (FundSubtype.BROAD_ETF, FundSubtype.BROAD_OEF):
        sip_note = "宽基指数适合长期定投"
    elif subtype == FundSubtype.SECTOR_ETF:
        sip_note = "行业 ETF 适合专项配置，不适合作为定投主仓"
        sip_score = 3
    else:
        sip_note = "主动基金可定投，但留意基金经理变更风险"
        sip_score = 4

    if premium is None or subtype in (FundSubtype.BROAD_OEF, FundSubtype.ACTIVE_OEF,
                                       FundSubtype.BOND_FUND, FundSubtype.MONEY_FUND):
        return sip_score + 5, sip_note
    if premium <= -0.5:
        prem_note = f"当前折价 {abs(premium):.2f}%，买入有安全垫"
        prem_score = 5
    elif premium <= 0.2:
        prem_note = f"溢折价 {premium:+.2f}%，接近净值，合理"
        prem_score = 5
    elif premium <= 0.5:
        prem_note = f"溢价 {premium:.2f}%，轻微"
        prem_score = 4
    elif premium <= 1.0:
        prem_note = f"溢价 {premium:.2f}%，留意追高风险"
        prem_score = 2
    else:
        prem_note = f"溢价 {premium:.2f}%，较高，建议等待回归净值"
        prem_score = 0
    return sip_score + prem_score, f"{sip_note}；{prem_note}"


# ── 主评分函数 ───────────────────────────────────────────

class FundRater:
    @staticmethod
    def rate(data: FundData) -> dict:
        """
        返回：
          score     int   总分 0-100
          grade     str   A / B / C / D
          conclusion str  中文结论语
          dimensions list  各维度详情
          reasoning  str  完整文字分析
        """
        st = data.subtype

        # 1. 产品质量 35分
        fee_score, fee_note     = _score_fee(data.fee_rate, st)
        aum_score, aum_note     = _score_aum(data.aum_bn, st)
        hist_score, hist_note   = _score_history(data.years_since_inception)
        te_score, te_note       = _score_tracking_error(data.tracking_error, st)
        product_score = fee_score + aum_score + hist_score + te_score   # /35

        # 2. 标的质量 35分（指数类型 25 + 估值 10）
        idx_score, idx_note     = _score_index_type(st, data.name)
        val_score, val_note     = _score_valuation(data.pe_percentile, st)
        target_score = idx_score + val_score   # /35

        # 3. 组合适配 20分
        port_score, port_note   = _score_portfolio_fit(st, data.existing_cn_codes, data.code)

        # 4. 交易执行 10分
        exec_score, exec_note   = _score_execution(st, data.premium_pct)

        total = product_score + target_score + port_score + exec_score

        # Grade mapping
        if total >= 82:
            grade = "A"
        elif total >= 68:
            grade = "B"
        elif total >= 52:
            grade = "C"
        else:
            grade = "D"

        conclusion = _build_conclusion(data, total, grade)

        # Nav string
        nav_str = f"¥{data.nav:.4f}" if data.nav else "N/A"
        chg_str = f"（{data.change_pct:+.2f}%）" if data.change_pct is not None else ""

        reasoning = _build_reasoning(data, total,
            fee_note, aum_note, hist_note, te_note,
            idx_note, val_note, port_note, exec_note,
            product_score, target_score, port_score, exec_score, nav_str, chg_str)

        dimensions = [
            {"label": "产品质量", "val": f"{product_score}/35",
             "detail": f"费率·{fee_note}；规模·{aum_note}；历史·{hist_note}"},
            {"label": "标的质量", "val": f"{target_score}/35",
             "detail": f"{idx_note}；{val_note}"},
            {"label": "组合适配", "val": f"{port_score}/20",  "detail": port_note},
            {"label": "交易执行", "val": f"{exec_score}/10",  "detail": exec_note},
        ]

        return {
            "score":      total,
            "grade":      grade,
            "conclusion": conclusion,
            "dimensions": dimensions,
            "reasoning":  reasoning,
            "subtype":    st.value,
            "subtype_label": SUBTYPE_LABEL[st],
            # 存入 DB 的字段
            "product_score": product_score,
            "target_score":  target_score,
            "port_score":    port_score,
            "exec_score":    exec_score,
        }


def _build_conclusion(data: FundData, score: int, grade: str) -> str:
    st = data.subtype
    pct = data.pe_percentile

    if st == FundSubtype.MONEY_FUND:
        return "现金管理工具，随时可用"
    if st == FundSubtype.BOND_FUND:
        return "稳健配置，适合降低组合波动"
    if grade == "D":
        if data.aum_bn is not None and data.aum_bn < 1:
            return "规模过小，清盘风险较高，不推荐"
        return "综合评分偏低，谨慎配置"
    if st in (FundSubtype.BROAD_ETF, FundSubtype.BROAD_OEF):
        if pct is not None and pct >= 80:
            return "宽基指数，估值偏高，建议等待或分批买入"
        if pct is not None and pct <= 30:
            return "宽基指数，当前估值合理偏低，适合定投"
        return "宽基指数，适合长期定投作为核心仓"
    if st == FundSubtype.SECTOR_ETF:
        if pct is not None and pct >= 80:
            return "行业估值偏高，等待回调后专项配置"
        return "行业/主题基金，适合专项配置，非核心仓"
    # 主动
    return "主动基金，关注基金经理稳定性，适合定投"


def _build_reasoning(data, total, fee_note, aum_note, hist_note, te_note,
                     idx_note, val_note, port_note, exec_note,
                     p, t, po, e, nav_str, chg_str) -> str:
    st_label = SUBTYPE_LABEL[data.subtype]
    lines = [
        f"{data.name}（{data.code}）为{st_label}，综合评分 {total}/100。",
        "",
        f"当前净值：{nav_str} {chg_str}",
        "",
        "━━ 产品质量 ━━",
        f"• {fee_note}",
        f"• {aum_note}",
        f"• {hist_note}",
    ]
    if te_note and "不考察" not in te_note:
        lines.append(f"• 跟踪误差：{te_note}")
    lines += [
        "",
        "━━ 标的质量 ━━",
        f"• {idx_note}",
        f"• 估值分位：{val_note}",
        "",
        "━━ 组合适配 ━━",
        f"• {port_note}",
        "",
        "━━ 交易执行 ━━",
        f"• {exec_note}",
    ]
    if data.subtype in (FundSubtype.BROAD_ETF, FundSubtype.BROAD_OEF):
        lines += ["", "建议：坚持定投，不做短期择时。"]
    elif data.subtype == FundSubtype.SECTOR_ETF:
        lines += ["", "建议：作为卫星仓，控制在总仓位 20% 以内。"]
    return "\n".join(lines)
