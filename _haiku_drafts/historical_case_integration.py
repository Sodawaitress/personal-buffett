"""
历史案例集成模块 - 将历史案例匹配和概率推导集成到投行级分析中

这个模块是连接层，负责：
1. 在分析任何新股票时自动调用案例匹配
2. 基于相似案例计算概率
3. 生成「历史对标」报告章节
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from case_matcher import CaseMatcher
from probability_inferencer import ProbabilityInferencer
import db


class HistoricalCaseAnalyzer:
    """
    历史案例分析器

    核心功能：
    1. 自动匹配相似历史案例
    2. 计算概率和预期收益
    3. 生成历史对标报告
    """

    def __init__(self):
        self.matcher = CaseMatcher(similarity_threshold=0.6)
        self.inferencer = ProbabilityInferencer()

    def analyze_with_historical_context(self, stock_data):
        """
        对股票进行分析，融合历史案例上下文

        Args:
            stock_data: dict with keys:
                - code: str
                - name: str
                - roe: float
                - net_margin: float
                - revenue_decline_pct: float
                - debt_ratio: float
                - industry: str
                - event_type: str
                - current_price: float

        Returns:
            dict: {
                'similar_cases': [...],
                'probabilities': {...},
                'expected_outcomes': {...},
                'warning_signals': {...},
                'success_factors': {...},
                'historical_report': str (HTML)
            }
        """
        # Step 1: 查找相似案例
        similar_cases = self.matcher.find_similar_cases(stock_data)

        # Step 2: 计算概率
        probabilities = self.inferencer.infer_probabilities(similar_cases)

        # Step 3: 推导预期收益
        expected_outcomes = self.inferencer.infer_average_outcome(similar_cases)

        # Step 4: 推导股价路径
        price_path = self.inferencer.infer_stock_price_path(
            similar_cases,
            stock_data.get('current_price', 0)
        )

        # Step 5: 提取预警信号和成功要素
        warning_signals = self.inferencer.extract_warning_signals(similar_cases)
        success_factors = self.inferencer.extract_success_factors(similar_cases)

        # Step 6: 生成历史对标报告
        historical_report = self._generate_historical_report(
            stock_data,
            similar_cases,
            probabilities,
            expected_outcomes,
            price_path,
            warning_signals,
            success_factors
        )

        return {
            'similar_cases': similar_cases,
            'probabilities': probabilities,
            'expected_outcomes': expected_outcomes,
            'price_path': price_path,
            'warning_signals': warning_signals,
            'success_factors': success_factors,
            'historical_report': historical_report
        }

    def _generate_historical_report(self, stock_data, similar_cases, probabilities,
                                   expected_outcomes, price_path, warning_signals,
                                   success_factors):
        """
        生成历史对标报告（HTML 格式）

        Returns:
            str: HTML 报告内容
        """
        html = f"""
        <div class="historical-analysis-section">
            <h2>IV. 历史案例对标</h2>

            <div class="section-summary">
                <p>基于财务特征和事件类型，系统找到 <strong>{probabilities['case_count']}</strong> 个相似的历史案例。
                以下为详细对标分析。</p>
            </div>

            <h3>找到的相似历史案例</h3>
            <table class="cases-table">
                <thead>
                    <tr>
                        <th>案例名称</th>
                        <th>相似度</th>
                        <th>结果</th>
                        <th>耗时</th>
                        <th>收益倍数</th>
                    </tr>
                </thead>
                <tbody>
        """

        for item in similar_cases:
            case = item['case']
            html += f"""
                    <tr>
                        <td><strong>{case['case_name']}</strong></td>
                        <td>{item['similarity_score']:.0%}</td>
                        <td>{self._outcome_label(case['outcome'])}</td>
                        <td>{case['reorganization_duration_months']} 个月</td>
                        <td>{case['multiple_achieved']:.1f}x</td>
                    </tr>
            """

        html += """
                </tbody>
            </table>

            <h3>概率分布（基于历史数据）</h3>
            <div class="probability-breakdown">
        """

        html += f"""
                <p><strong>成功（完全重整）</strong>: {probabilities['success']:.0%}</p>
                <p><strong>部分成功</strong>: {probabilities['partial_success']:.0%}</p>
                <p><strong>失败</strong>: {probabilities['failure']:.0%}</p>
                <p><strong>退市</strong>: {probabilities['delisted']:.0%}</p>
        """

        html += """
            </div>

            <h3>预期结果</h3>
            <div class="expected-outcomes">
        """

        if expected_outcomes.get('expected_multiple'):
            html += f"""
                <p><strong>期望收益倍数</strong>: {expected_outcomes['expected_multiple']:.1f}x</p>
                <p><strong>期望收益率</strong>: {expected_outcomes['expected_return_pct']:.0f}%</p>
                <p><strong>平均周期</strong>: {expected_outcomes['expected_duration_months']} 个月</p>
            """

        html += """
            </div>

            <h3>股价路径预期</h3>
            <div class="price-path">
                <p>基于相似案例历史股价走势，推导当前股票可能的路径：</p>
                <ul>
        """

        if price_path:
            for month, price in sorted(price_path.items()):
                html += f"<li>{month}: ¥{price:.2f}</li>"

        html += """
                </ul>
            </div>

            <h3>关键成功要素</h3>
            <div class="success-factors">
        """

        if success_factors.get('success_keys'):
            html += "<ul>"
            for factor, count in success_factors['common_success_factors']:
                html += f"<li>{factor} (出现 {count} 次)</li>"
            html += "</ul>"
        else:
            html += "<p>未识别出明确的成功要素</p>"

        html += """
            </div>

            <h3>风险预警信号</h3>
            <div class="warning-signals">
        """

        if warning_signals.get('what_to_watch_for'):
            html += "<p><strong>需要重点关注的信号：</strong></p><ul>"
            for signal, count in warning_signals['common_failure_signals']:
                html += f"<li>{signal} (在失败案例中出现 {count} 次)</li>"
            html += "</ul>"
        else:
            html += "<p>相似案例中未识别出明确的失败信号</p>"

        html += """
            </div>

            <h3>历史启示</h3>
            <div class="lessons-learned">
                <ul>
        """

        for item in similar_cases[:3]:  # 展示前 3 个案例的经验
            case = item['case']
            html += f"""
                <li>
                    <strong>{case['case_name']}</strong>: {case['lessons_learned']}
                </li>
            """

        html += """
                </ul>
            </div>

            <h3>总结</h3>
            <div class="conclusion">
                <p>本次分析基于 """ + str(probabilities['case_count']) + """ 个相似的历史案例。
                这些案例提供了可追溯、可验证的参考数据，提高了分析的可信度。</p>
            </div>
        </div>
        """

        return html

    @staticmethod
    def _outcome_label(outcome):
        """生成结果标签"""
        labels = {
            'success': '✅ 成功',
            'partial_success': '⚠️ 部分成功',
            'failure': '❌ 失败',
            'delisted': '🗑️ 退市'
        }
        return labels.get(outcome, outcome)


# ══════════════════════════════════════════════════
# 集成到投行分析框架
# ══════════════════════════════════════════════════

def enhance_investment_analysis(base_analysis, stock_data):
    """
    增强投行分析：添加历史案例对标部分

    Args:
        base_analysis: dict, 原始投行分析结果
        stock_data: dict, 股票数据

    Returns:
        dict: 融合了历史对标的完整分析
    """
    analyzer = HistoricalCaseAnalyzer()
    historical_context = analyzer.analyze_with_historical_context(stock_data)

    # 将历史分析融入到基础分析中
    enhanced_analysis = base_analysis.copy()
    enhanced_analysis['historical_context'] = historical_context
    enhanced_analysis['historical_report'] = historical_context['historical_report']

    # 调整概率
    if historical_context['probabilities']['case_count'] > 0:
        enhanced_analysis['probability_success'] = historical_context['probabilities']['success']
        enhanced_analysis['probability_failure'] = historical_context['probabilities']['failure']
        enhanced_analysis['probability_delisted'] = historical_context['probabilities']['delisted']

    return enhanced_analysis


# ══════════════════════════════════════════════════
# 测试代码
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    print("【历史案例集成模块测试】\n")

    analyzer = HistoricalCaseAnalyzer()

    # 模拟 *ST华闻 的分析数据
    st_huawen_data = {
        'code': '000793',
        'name': '*ST华闻',
        'roe': -120,
        'net_margin': -85,
        'revenue_decline_pct': 91.4,
        'debt_ratio': 79,
        'industry': 'Media',
        'event_type': 'reorganization',
        'current_price': 3.0
    }

    # 执行分析
    result = analyzer.analyze_with_historical_context(st_huawen_data)

    print("相似案例:")
    for item in result['similar_cases']:
        print(f"  - {item['case']['case_name']}: 相似度 {item['similarity_score']:.0%}")

    print("\n概率分布:")
    print(f"  - 成功: {result['probabilities']['success']:.0%}")
    print(f"  - 部分成功: {result['probabilities']['partial_success']:.0%}")
    print(f"  - 失败: {result['probabilities']['failure']:.0%}")
    print(f"  - 退市: {result['probabilities']['delisted']:.0%}")

    print("\n预期结果:")
    print(f"  - 期望倍数: {result['expected_outcomes'].get('expected_multiple', 'N/A')}x")
    print(f"  - 期望收益率: {result['expected_outcomes'].get('expected_return_pct', 'N/A')}%")

    print("\n✓ 测试完成！")
