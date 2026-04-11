#!/usr/bin/env python3
"""
历史案例框架使用示例 - 展示如何在实际投行分析中使用

这个脚本演示了如何快速为任何股票生成「有历史依据的」分析报告
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from scripts.historical_case_integration import HistoricalCaseAnalyzer


def generate_investment_report(stock_code, stock_name, financial_data):
    """
    生成投行级报告（包含历史对标）

    Args:
        stock_code: str, 股票代码
        stock_name: str, 股票名称
        financial_data: dict, 财务数据

    Returns:
        str: 完整的投行级报告（文本格式）
    """

    analyzer = HistoricalCaseAnalyzer()

    # 准备分析数据
    stock_data = {
        'code': stock_code,
        'name': stock_name,
        **financial_data
    }

    # 执行分析
    result = analyzer.analyze_with_historical_context(stock_data)

    # 生成报告
    report = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                        投行级股票分析报告
║                   基于历史案例的数据驱动分析
╚═══════════════════════════════════════════════════════════════════════════╝

【股票信息】
─────────────────────────────────────────────────────────────────────────────
代码: {stock_code}
名称: {stock_name}
行业: {financial_data.get('industry', 'N/A')}
事件类型: {financial_data.get('event_type', 'N/A')}
当前股价: ¥{financial_data.get('current_price', 'N/A')}

【财务指标】
─────────────────────────────────────────────────────────────────────────────
ROE: {financial_data.get('roe', 'N/A')}%
净利润率: {financial_data.get('net_margin', 'N/A')}%
收入下滑: {financial_data.get('revenue_decline_pct', 'N/A')}%
债务比: {financial_data.get('debt_ratio', 'N/A')}%

【历史案例对标】
─────────────────────────────────────────────────────────────────────────────
系统在历史案例库中找到 {result['probabilities']['case_count']} 个相似案例。

相似案例（按相似度排序）：
"""

    for i, item in enumerate(result['similar_cases'], 1):
        case = item['case']
        report += f"""
{i}. {case['case_name']}
   相似度: {item['similarity_score']:.0%}
   结果: {item['outcome'].upper()}
   耗时: {case['reorganization_duration_months']} 个月
   收益倍数: {case['multiple_achieved']:.1f}x
"""

    report += f"""
【概率分布（基于历史数据统计）】
─────────────────────────────────────────────────────────────────────────────
成功（完全重整）: {result['probabilities']['success']:.1%}
部分成功: {result['probabilities']['partial_success']:.1%}
失败: {result['probabilities']['failure']:.1%}
退市: {result['probabilities']['delisted']:.1%}

这些概率是基于 {result['probabilities']['case_count']} 个相似历史案例的统计结果。
"""

    if result['expected_outcomes']:
        report += f"""
【预期结果】
─────────────────────────────────────────────────────────────────────────────
期望收益倍数: {result['expected_outcomes'].get('expected_multiple', 'N/A'):.1f}x
期望收益率: {result['expected_outcomes'].get('expected_return_pct', 'N/A'):.0f}%
平均周期: {result['expected_outcomes'].get('expected_duration_months', 'N/A')} 个月
"""

    if result['price_path']:
        report += f"""
【股价路径预期】
─────────────────────────────────────────────────────────────────────────────
基于相似案例历史股价，推导当前股票可能的发展路径：
"""
        for month, price in sorted(result['price_path'].items()):
            report += f"\n{month.replace('_', ' ').upper()}: ¥{price:.2f}"

    if result['success_factors'].get('success_keys'):
        report += f"""

【关键成功要素】
─────────────────────────────────────────────────────────────────────────────
从成功案例中提取的共同特征：
"""
        for factor, count in result['success_factors']['common_success_factors']:
            report += f"\n• {factor} (在 {count} 个成功案例中出现)"

    if result['warning_signals'].get('what_to_watch_for'):
        report += f"""

【风险预警信号】
─────────────────────────────────────────────────────────────────────────────
需要重点监控的风险信号（来自失败案例）：
"""
        for signal, count in result['warning_signals']['common_failure_signals']:
            report += f"\n⚠️  {signal} (在 {count} 个失败案例中出现)"

    report += f"""

【历史启示与建议】
─────────────────────────────────────────────────────────────────────────────
本次分析基于 {result['probabilities']['case_count']} 个真实历史案例。每个概率、预期和信号都可
追溯到具体的参考案例，确保了分析的透明性和可验证性。

建议监控的事项：
1. 定期追踪与参考案例相同的发展阶段
2. 关注预警信号是否出现
3. 对比成功要素是否逐步落实

【风险提示】
─────────────────────────────────────────────────────────────────────────────
• 历史不会完全重复，但会有相似的模式
• 本分析基于历史数据，不能保证未来结果
• 请结合其他分析方法做出投资决策

═══════════════════════════════════════════════════════════════════════════
报告生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
分析框架版本: 1.0
═══════════════════════════════════════════════════════════════════════════
"""

    return report


# ══════════════════════════════════════════════════════════════════════════
# 使用示例
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n【历史案例框架实际使用演示】\n")

    # 示例 1: 分析 *ST华闻
    print("=" * 80)
    print("示例 1: 分析 *ST华闻 (000793)")
    print("=" * 80)

    st_huawen_data = {
        'roe': -120,
        'net_margin': -85,
        'revenue_decline_pct': 91.4,
        'debt_ratio': 79,
        'industry': 'Media',
        'event_type': 'reorganization',
        'current_price': 3.0
    }

    report_1 = generate_investment_report('000793', '*ST华闻', st_huawen_data)
    print(report_1)

    # 示例 2: 分析另一只假设的 ST 股票
    print("\n\n" + "=" * 80)
    print("示例 2: 分析 *ST新能 (假设，能源行业)")
    print("=" * 80)

    st_xineng_data = {
        'roe': -75,
        'net_margin': -62,
        'revenue_decline_pct': 80,
        'debt_ratio': 82,
        'industry': 'Energy',
        'event_type': 'reorganization',
        'current_price': 2.5
    }

    report_2 = generate_investment_report('600XXX', '*ST新能', st_xineng_data)
    print(report_2)

    print("\n" + "=" * 80)
    print("✓ 演示完成！")
    print("=" * 80)
    print("""
【框架的核心价值】

1. 数据驱动
   - 每个概率都有历史数据支撑
   - 可追溯、可验证

2. 可复用
   - 对任何新股票都适用
   - 无需修改代码，只需提供财务数据

3. 透明
   - 用户看得到参考案例
   - 理解每个结论的来源

4. 可扩展
   - 加入新案例后自动生效
   - 支持多行业、多事件类型

这个框架解决的核心问题是：
"我怎么知道你的分析不是凭空想象？"

答案是：
"我查了 N 个相似的历史案例，其中 X 个成功、Y 个失败。这是基于真实数据。"
""")
