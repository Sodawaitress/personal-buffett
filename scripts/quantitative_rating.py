#!/usr/bin/env python3
"""
定量化巴菲特评级系统
完全基于财务数据，无需 LLM
所有规则来自 buffett_analyst.py 中的既有框架
"""

import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class QuantitativeRater:
    """基于数据的巴菲特评级引擎"""

    def __init__(self):
        """初始化评分规则"""
        pass

    # ─────────────────────────────────────────────────────────
    # 第一维：护城河评分 (40 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_roe(roe_pct: float) -> Tuple[int, str]:
        """
        ROE 评分 (15 分)
        来自 SYSTEM_LETTER: "ROE < 5% → 赚钱能力几乎为零"
        """
        if roe_pct > 25:
            return 15, "超强竞争优势（ROE > 25%）"
        elif roe_pct > 20:
            return 13, "优秀盈利能力（ROE > 20%）"
        elif roe_pct > 15:
            return 10, "良好盈利能力（ROE > 15%）"
        elif roe_pct > 10:
            return 7, "一般盈利能力（ROE > 10%）"
        elif roe_pct > 5:
            return 3, "弱盈利能力（5% < ROE < 10%）"
        elif roe_pct >= 0:
            return 0, "⚠️ 赚钱能力几乎为零（0 < ROE < 5%）"
        else:
            return -5, "🚨 公司在亏损（ROE < 0%）"

    @staticmethod
    def score_net_margin(margin_pct: float) -> Tuple[int, str]:
        """
        净利率评分 (10 分)
        来自 SYSTEM_LETTER: "净利率 < 0% → 公司在烧钱"
        """
        if margin_pct > 25:
            return 10, "极强定价权（净利率 > 25%）"
        elif margin_pct > 15:
            return 8, "很强定价权（净利率 > 15%）"
        elif margin_pct > 10:
            return 6, "中等定价权（净利率 > 10%）"
        elif margin_pct > 5:
            return 4, "弱定价权（5% < 净利率 < 10%）"
        elif margin_pct >= 0:
            return 2, "极弱定价权（0 < 净利率 < 5%）"
        else:
            return -5, "🚨 公司在烧钱（净利率 < 0%）"

    @staticmethod
    def score_roe_stability(roe_list: List[float]) -> Tuple[int, str]:
        """
        ROE 稳定性评分 (10 分)
        来自 SYSTEM_LETTER: "波动 < 10% → 护城河稳固"

        Args:
            roe_list: 过去5年的ROE（百分比），从新到旧排列
        """
        if len(roe_list) < 2:
            return 5, "数据不足（年份 < 2）"

        # 计算变异系数（衡量相对波动）
        avg_roe = sum(roe_list) / len(roe_list)
        if avg_roe == 0:
            volatility = float('inf')
        else:
            variance = sum((x - avg_roe) ** 2 for x in roe_list) / len(roe_list)
            std_dev = variance ** 0.5
            volatility = std_dev / abs(avg_roe)

        if volatility < 0.10:
            return 10, "非常稳定（波动 < 10%）"
        elif volatility < 0.20:
            return 8, "较稳定（波动 10-20%）"
        elif volatility < 0.30:
            return 5, "一般稳定（波动 20-30%）"
        elif volatility < 0.50:
            return 3, "波动较大（波动 30-50%）"
        else:
            return -3, "⚠️ 波动剧烈（波动 > 50%）"

    @staticmethod
    def score_fcf_quality(fcf_ratio: Optional[float]) -> Tuple[int, str]:
        """
        现金流质量评分 (5 分)
        FCF 比率 = 营运现金流 / 净利润
        """
        if fcf_ratio is None:
            return 3, "数据缺失"

        if fcf_ratio >= 1.0:
            return 5, "利润质量优秀（FCF > 1.0x）"
        elif fcf_ratio >= 0.8:
            return 4, "利润质量良好（FCF 0.8-1.0x）"
        elif fcf_ratio >= 0.5:
            return 2, "利润质量一般（FCF 0.5-0.8x）"
        else:
            return -2, "⚠️ 利润质量差（FCF < 0.5x）"

    @classmethod
    def score_moat(cls, annual_data: List[Dict], signals: Dict = None) -> Tuple[int, List[str]]:
        """
        护城河总分 (40 分)

        Args:
            annual_data: 财务数据列表
            signals: 实时信号（如 yfinance 数据）

        Returns:
            (总分, 明细说明列表)
        """
        details = []
        total = 0

        if not annual_data and not signals:
            return 0, ["护城河数据不足"]

        # 优先从 annual_data 获取最新数据
        if annual_data:
            latest = annual_data[0]
            roe_pct = float(str(latest.get("roe", "0%")).strip("%"))
            margin_pct = float(str(latest.get("net_margin", "0%")).strip("%"))
            roe_list = [float(str(y.get("roe", "0%")).strip("%")) for y in annual_data[:5]]
        elif signals:
            # 从 signals (yfinance) 获取
            # yfinance 的 roe 通常是 0.25 (25%)，也可能是 1.5 (150%)
            roe_val = signals.get("roe")
            if roe_val is not None:
                roe_pct = roe_val * 100
            else:
                roe_pct = 0
            
            margin_val = signals.get("profit_margin")
            if margin_val is not None:
                margin_pct = margin_val * 100
            else:
                margin_pct = 0
            
            roe_list = [roe_pct] # 只有当前数据
        else:
            roe_pct = 0
            margin_pct = 0
            roe_list = []

        # ROE 评分
        roe_score, roe_desc = cls.score_roe(roe_pct)
        details.append(f"ROE: {roe_score}/15 分 - {roe_desc}")
        total += roe_score

        # 净利率评分
        margin_score, margin_desc = cls.score_net_margin(margin_pct)
        details.append(f"净利率: {margin_score}/10 分 - {margin_desc}")
        total += margin_score

        # ROE 稳定性
        stability_score, stability_desc = cls.score_roe_stability(roe_list)
        details.append(f"ROE 稳定性: {stability_score}/10 分 - {stability_desc}")
        total += stability_score

        # FCF 质量
        fcf_score = 3
        fcf_desc = "数据不足"
        if annual_data and "ocf_per_share" in annual_data[0] and "eps" in annual_data[0]:
            try:
                latest = annual_data[0]
                ocf = float(latest["ocf_per_share"])
                eps = float(latest["eps"])
                fcf_ratio = ocf / eps if eps != 0 else None
                fcf_score, fcf_desc = cls.score_fcf_quality(fcf_ratio)
            except:
                pass
        elif signals and "fcf_quality_avg" in signals:
            fcf_score, fcf_desc = cls.score_fcf_quality(signals["fcf_quality_avg"])
        
        details.append(f"现金流质量: {fcf_score}/5 分 - {fcf_desc}")
        total += fcf_score

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第二维：增长与管理层 (25 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_profit_growth(profit_list: List[float], years: int = 3) -> Tuple[int, str]:
        """
        利润增长评分 (12 分)

        Args:
            profit_list: 净利润列表（从新到旧）
            years: 计算CAGR的年数
        """
        if len(profit_list) < 2:
            return 0, "数据不足"

        recent = profit_list[:years]
        if recent[0] <= 0 or recent[-1] <= 0:
            return 0, "存在亏损年份"

        # 计算 CAGR
        cagr = (recent[0] / recent[-1]) ** (1 / (len(recent) - 1)) - 1
        cagr_pct = cagr * 100

        if cagr_pct > 30:
            return 12, f"高速增长（CAGR {cagr_pct:.1f}%）"
        elif cagr_pct > 15:
            return 10, f"快速增长（CAGR {cagr_pct:.1f}%）"
        elif cagr_pct > 10:
            return 8, f"良好增长（CAGR {cagr_pct:.1f}%）"
        elif cagr_pct > 5:
            return 5, f"适度增长（CAGR {cagr_pct:.1f}%）"
        elif cagr_pct >= 0:
            return 2, f"缓慢增长（CAGR {cagr_pct:.1f}%）"
        else:
            return -5, f"🚨 利润衰退（CAGR {cagr_pct:.1f}%）"

    @staticmethod
    def score_profit_consistency(profit_list: List[float]) -> Tuple[int, str]:
        """
        利润增长一致性评分 (8 分)
        检查是否有连续亏损
        """
        if len(profit_list) < 3:
            return 4, "数据不足"

        recent_3y = profit_list[:3]
        negative_count = sum(1 for p in recent_3y if p < 0)

        if negative_count == 0:
            return 8, "连续盈利（过去3年无亏损）"
        elif negative_count == 1:
            return 5, "基本盈利（1年亏损）"
        elif negative_count == 2:
            return 1, "⚠️ 多年亏损（2年亏损）"
        else:
            return -5, "🚨 连续亏损（3年都亏）"

    @staticmethod
    def score_management(news_signals: Dict) -> Tuple[int, str]:
        """
        管理层信号评分 (5 分)
        来自 _analyze_news_signals()
        """
        score = 2  # 基础分
        reasons = []

        # 正面信号：回购 > 分红 > 维持现状
        if news_signals.get("high_pos_buyback", 0) > 0:
            score += 2
            reasons.append("有回购行动")
        elif news_signals.get("mid_pos_dividend", 0) > 0:
            score += 1
            reasons.append("有分红计划")

        # 负面信号：离职 / 减持
        if news_signals.get("high_neg_resignation", 0) > 0:
            score -= 2
            reasons.append("🚨 CEO/CFO 离职")

        if news_signals.get("mid_neg_reduction", 0) > 0:
            score -= 1
            reasons.append("管理层减持")

        desc = "；".join(reasons) if reasons else "管理层信号平常"
        return max(0, min(5, score)), desc

    @classmethod
    def score_growth_and_management(cls, annual_data: List[Dict],
                                    news_signals: Dict) -> Tuple[int, List[str]]:
        """
        增长与管理层总分 (25 分)
        """
        details = []
        total = 0

        # 提取净利润列表
        profit_list = []
        for year_data in annual_data:
            try:
                # 尝试从 net_profit 字段提取（格式可能是 "439.45亿"）
                np_str = year_data.get("net_profit", "0")
                if isinstance(np_str, str):
                    np_str = np_str.replace("亿", "").replace("万", "")
                profit_list.append(float(np_str))
            except:
                pass

        # 利润增长
        if profit_list:
            growth_score, growth_desc = cls.score_profit_growth(profit_list)
            details.append(f"利润增长: {growth_score}/12 分 - {growth_desc}")
            total += growth_score

            # 利润一致性
            consistency_score, consistency_desc = cls.score_profit_consistency(profit_list)
            details.append(f"利润一致性: {consistency_score}/8 分 - {consistency_desc}")
            total += consistency_score
        else:
            total += 10  # 默认分
            details.append("利润数据: 10/20 分 - 数据缺失")

        # 管理层信号
        mgmt_score, mgmt_desc = cls.score_management(news_signals)
        details.append(f"管理层: {mgmt_score}/5 分 - {mgmt_desc}")
        total += mgmt_score

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第三维：财务安全性 (20 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_debt(debt_to_equity: float) -> Tuple[int, str]:
        """
        负债风险评分 (10 分)
        来自 SYSTEM_LETTER: "债务比 > 20 → 高杠杆风险"
        注：债务比通常指 D/E，这里直接用
        """
        if debt_to_equity < 0.3:
            return 10, "很低风险（D/E < 0.3）"
        elif debt_to_equity < 0.5:
            return 8, "低风险（D/E 0.3-0.5）"
        elif debt_to_equity < 0.8:
            return 6, "中等风险（D/E 0.5-0.8）"
        elif debt_to_equity < 1.0:
            return 4, "较高风险（D/E 0.8-1.0）"
        elif debt_to_equity < 2.0:
            return 2, "⚠️ 高风险（D/E 1.0-2.0）"
        else:
            return -5, "🚨 极度高杠杆（D/E > 2.0）"

    @staticmethod
    def score_profitability_sustainability(profit_list: List[float]) -> Tuple[int, str]:
        """
        盈利可持续性评分 (10 分)
        """
        if len(profit_list) < 3:
            return 5, "数据不足"

        recent_3y = profit_list[:3]
        positive_count = sum(1 for p in recent_3y if p > 0)

        if positive_count == 3:
            return 10, "很好（连续3年盈利）"
        elif positive_count == 2:
            return 6, "一般（2年盈利）"
        elif positive_count == 1:
            return 2, "⚠️ 较差（1年盈利）"
        else:
            return -5, "🚨 破产风险（连续亏损）"

    @classmethod
    def score_safety(cls, annual_data: List[Dict], signals: Dict = None) -> Tuple[int, List[str]]:
        """
        财务安全性总分 (20 分)
        """
        details = []
        total = 0

        if not annual_data and not signals:
            return 0, ["安全性数据不足"]

        # 负债评分
        debt_ratio = None
        if annual_data:
            latest = annual_data[0]
            try:
                # A股通常是 "61.17%"
                debt_ratio = float(str(latest.get("debt_ratio", "0%")).strip("%")) / 100
            except:
                pass
        
        if debt_ratio is None and signals:
            # yfinance: debtToEquity (e.g., 102.63 for 102.63%)
            # 或者是 0.5 (50%)
            de = signals.get("debt_to_equity")
            if de is not None:
                if de > 2.0: # 认为是百分比
                    debt_ratio = de / 100
                else:
                    debt_ratio = de

        if debt_ratio is not None:
            debt_score, debt_desc = cls.score_debt(debt_ratio)
            details.append(f"负债风险: {debt_score}/10 分 - {debt_desc}")
            total += debt_score
        else:
            total += 5
            details.append("负债风险: 5/10 分 - 数据缺失")

        # 盈利可持续性
        profit_list = []
        if annual_data:
            for year_data in annual_data:
                try:
                    np_str = year_data.get("net_profit", "0")
                    if isinstance(np_str, str):
                        np_str = np_str.replace("亿", "").replace("万", "")
                    profit_list.append(float(np_str))
                except:
                    pass
        elif signals:
            # 如果没有历史数据，至少根据当前判断
            pm = signals.get("profit_margin", 0)
            if pm is not None and pm > 0:
                profit_list = [1.0, 1.0, 1.0] # 模拟盈利
            elif pm is not None and pm < 0:
                profit_list = [-1.0, -1.0, -1.0] # 模拟亏损

        if profit_list:
            sust_score, sust_desc = cls.score_profitability_sustainability(profit_list)
            details.append(f"盈利可持续性: {sust_score}/10 分 - {sust_desc}")
            total += sust_score
        else:
            total += 5
            details.append("盈利可持续性: 5/10 分 - 数据缺失")

        return total, details

    # ─────────────────────────────────────────────────────────
    # 第四维：估值 (15 分)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def score_pe_valuation(pe_percentile: Optional[int]) -> Tuple[int, str]:
        """
        PE 估值评分 (7 分)
        百分位：0% = 5年最低，100% = 5年最高
        """
        if pe_percentile is None:
            return 3, "数据缺失"

        if pe_percentile <= 20:
            return 7, "便宜（PE 百分位 0-20%）"
        elif pe_percentile <= 40:
            return 5, "略便宜（PE 百分位 20-40%）"
        elif pe_percentile <= 60:
            return 3, "平价（PE 百分位 40-60%）"
        elif pe_percentile <= 80:
            return 1, "⚠️ 略贵（PE 百分位 60-80%）"
        else:
            return -2, "🚨 贵（PE 百分位 > 80%）"

    @staticmethod
    def score_pb_valuation(pb_percentile: Optional[int]) -> Tuple[int, str]:
        """
        PB 估值评分 (5 分)
        """
        if pb_percentile is None:
            return 2, "数据缺失"

        if pb_percentile <= 20:
            return 5, "便宜（PB 百分位 0-20%）"
        elif pb_percentile <= 40:
            return 4, "略便宜（PB 百分位 20-40%）"
        elif pb_percentile <= 60:
            return 2, "平价（PB 百分位 40-60%）"
        elif pb_percentile <= 80:
            return 1, "⚠️ 略贵（PB 百分位 60-80%）"
        else:
            return -1, "贵（PB 百分位 > 80%）"

    @staticmethod
    def score_price_position(price_52week_pct: Optional[float]) -> Tuple[int, str]:
        """
        52周价格位置评分 (3 分)
        0% = 年低，100% = 年高
        """
        if price_52week_pct is None:
            return 0, "数据缺失"

        if price_52week_pct >= 90:
            return -3, "🚨 接近年高（> 90%），买入风险大"
        elif price_52week_pct >= 80:
            return -1, "⚠️ 年高附近"
        elif price_52week_pct <= 10:
            return 3, "接近年低（< 10%），买入机会"
        elif price_52week_pct <= 20:
            return 2, "年低附近"
        else:
            return 1, "中等位置"

    @classmethod
    def score_valuation(cls, pe_percentile: Optional[int], pb_percentile: Optional[int],
                       price_52week_pct: Optional[float]) -> Tuple[int, List[str]]:
        """
        估值总分 (15 分)
        """
        details = []
        total = 0

        # PE 估值
        pe_score, pe_desc = cls.score_pe_valuation(pe_percentile)
        details.append(f"PE 估值: {pe_score}/7 分 - {pe_desc}")
        total += pe_score

        # PB 估值
        pb_score, pb_desc = cls.score_pb_valuation(pb_percentile)
        details.append(f"PB 估值: {pb_score}/5 分 - {pb_desc}")
        total += pb_score

        # 价格位置
        pos_score, pos_desc = cls.score_price_position(price_52week_pct)
        details.append(f"52周位置: {pos_score}/3 分 - {pos_desc}")
        total += pos_score

        return total, details

    # ─────────────────────────────────────────────────────────
    # 最终评级转换
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def get_grade_and_conclusion(score: int) -> Dict:
        """
        根据综合得分生成评级
        """
        if score >= 85:
            return {
                "grade": "A",
                "conclusion": "买入",
                "emoji": "🟢",
                "rating_desc": "优秀公司 + 便宜价格"
            }
        elif score >= 75:
            return {
                "grade": "B+",
                "conclusion": "买入",
                "emoji": "🟢",
                "rating_desc": "不错的公司 + 合理价格"
            }
        elif score >= 65:
            return {
                "grade": "B",
                "conclusion": "持有",
                "emoji": "🟡",
                "rating_desc": "一般公司 + 平价"
            }
        elif score >= 55:
            return {
                "grade": "B-",
                "conclusion": "持有",
                "emoji": "🟡",
                "rating_desc": "一般公司，需要观察"
            }
        elif score >= 45:
            return {
                "grade": "C+",
                "conclusion": "观察",
                "emoji": "🟠",
                "rating_desc": "有风险信号，不建议介入"
            }
        elif score >= 35:
            return {
                "grade": "C",
                "conclusion": "减持",
                "emoji": "🔴",
                "rating_desc": "问题公司，应减仓"
            }
        else:
            return {
                "grade": "D",
                "conclusion": "卖出",
                "emoji": "🔴",
                "rating_desc": "极度风险，应立即卖出"
            }

    # ─────────────────────────────────────────────────────────
    # 红旗提取
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def extract_red_flags(annual_data: List[Dict], pe_pct: Optional[int],
                         price_52week_pct: Optional[float],
                         news_signals: Dict) -> List[str]:
        """
        提取所有红旗
        这些风险不能被好消息掩盖
        """
        flags = []

        if not annual_data:
            return flags

        latest = annual_data[0]

        # ROE 红旗
        try:
            roe_pct = float(latest.get("roe", "0%").strip("%"))
            if roe_pct < 5 and roe_pct >= 0:
                flags.append("🚨 ROE < 5%：赚钱能力几乎为零")
            elif roe_pct < 0:
                flags.append("🚨 ROE < 0%：公司在亏损")
        except:
            pass

        # 利润率红旗
        try:
            margin_pct = float(latest.get("net_margin", "0%").strip("%"))
            if margin_pct < 0:
                flags.append("🚨 净利率 < 0%：公司在烧钱")
        except:
            pass

        # 债务红旗
        try:
            debt_ratio = float(latest.get("debt_ratio", "0%").strip("%")) / 100
            if debt_ratio > 2.0:
                flags.append("🚨 债务比 > 2.0：极度高杠杆")
        except:
            pass

        # 价格位置红旗
        if price_52week_pct is not None and price_52week_pct > 90:
            flags.append(f"🚨 52周价格位置 {price_52week_pct:.0f}%：接近年高，买入风险大")

        # 连续亏损
        profit_list = []
        for year_data in annual_data[:3]:
            try:
                np_str = year_data.get("net_profit", "0")
                if isinstance(np_str, str):
                    np_str = np_str.replace("亿", "").replace("万", "")
                profit_list.append(float(np_str))
            except:
                pass

        if len(profit_list) >= 3 and all(p < 0 for p in profit_list):
            flags.append("🚨 连续 3 年亏损：破产风险")

        # 管理层离职红旗
        if news_signals.get("high_neg_resignation", 0) > 0:
            flags.append("🚨 CEO/CFO 离职：管理层信号警惕")

        # 资金大幅流出（如果有数据）
        if news_signals.get("fund_flow_ratio", 0) < -5:
            flags.append("🚨 主力资金大幅净流出：机构在离场")

        return flags

    # ─────────────────────────────────────────────────────────
    # 主评级函数
    # ─────────────────────────────────────────────────────────

    @classmethod
    def rate_stock(cls, code: str, name: str, annual_data: List[Dict],
                   pe_percentile: Optional[int], pb_percentile: Optional[int],
                   price_52week_pct: Optional[float],
                   news_signals: Dict,
                   signals: Dict = None) -> Dict:
        """
        完整评级函数

        Args:
            code: 股票代码
            name: 股票名称
            annual_data: 财务数据（从新到旧）
            pe_percentile: PE 百分位（0-100）
            pb_percentile: PB 百分位（0-100）
            price_52week_pct: 52周价格位置（0-100）
            news_signals: 新闻信号字典
            signals: 实时信号（如 yfinance 数据）
        """

        # 四个维度评分
        moat_score, moat_details = cls.score_moat(annual_data, signals=signals)
        growth_score, growth_details = cls.score_growth_and_management(annual_data, news_signals)
        safety_score, safety_details = cls.score_safety(annual_data, signals=signals)
        valuation_score, valuation_details = cls.score_valuation(pe_percentile, pb_percentile, price_52week_pct)

        # 总分
        total_score = moat_score + growth_score + safety_score + valuation_score

        # 评级
        grade_info = cls.get_grade_and_conclusion(total_score)

        # 红旗
        red_flags = cls.extract_red_flags(annual_data, pe_percentile, price_52week_pct, news_signals)

        # 生成理由总结
        reasoning = f"综合评分 {total_score}/100：{grade_info['rating_desc']}"
        if red_flags:
            reasoning += f"\n⚠️ 风险：{red_flags[0]}"

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
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


# ─────────────────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    rater = QuantitativeRater()

    # 示例：平安（000333）
    annual_data_demo = [
        {
            "year": "2025",
            "roe": "19.70%",
            "net_margin": "9.75%",
            "debt_ratio": "61.17%",
            "net_profit": "439.45亿",
            "eps": "5.8000",
            "ocf_per_share": "7.02",
            "bvps": "29.38"
        },
        {
            "year": "2024",
            "roe": "21.29%",
            "net_margin": "9.52%",
            "debt_ratio": "62.33%",
            "net_profit": "385.37亿",
            "eps": "5.4400",
            "ocf_per_share": "7.90",
            "bvps": "28.31"
        },
        {
            "year": "2023",
            "roe": "22.23%",
            "net_margin": "9.07%",
            "debt_ratio": "64.14%",
            "net_profit": "337.20亿",
            "eps": "4.9300",
            "ocf_per_share": "8.24",
            "bvps": "23.18"
        },
    ]

    result = rater.rate_stock(
        code="000333",
        name="中国平安",
        annual_data=annual_data_demo,
        pe_percentile=65,
        pb_percentile=55,
        price_52week_pct=72,
        news_signals={"high_pos_buyback": 1}
    )

    print(f"\n{'='*60}")
    print(f"【{result['name']}（{result['code']}）】")
    print(f"{'='*60}")
    print(f"综合得分: {result['score']}/100 → {result['emoji']} {result['grade']} 级 - {result['conclusion']}")
    print(f"\n【维度分析】")
    max_scores = {
        "moat": 40,
        "growth_management": 25,
        "safety": 20,
        "valuation": 15,
    }
    for dim_name, (score, details) in result['components'].items():
        max_score = max_scores.get(dim_name, 100)
        print(f"\n{dim_name.upper()}: {score}/{max_score}")
        for detail in details:
            print(f"  {detail}")

    if result['red_flags']:
        print(f"\n【风险旗子】")
        for flag in result['red_flags']:
            print(f"  {flag}")

    print(f"\n【总体判断】")
    print(f"  {result['reasoning']}")
    print(f"\n更新于: {result['timestamp']}")
