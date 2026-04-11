"""
概率推导引擎 - 从历史案例统计出有根据的概率

这个模块实现了：
1. 从相似案例中统计各个结果的出现频率
2. 计算有根据的概率分布
3. 推导预期的股价路径和收益倍数
"""

import json
import numpy as np
from collections import Counter


class ProbabilityInferencer:
    """
    概率推导引擎

    核心逻辑：
    1. 输入：找到的相似历史案例列表
    2. 统计：这些案例中有多少成功、多少失败等
    3. 输出：有根据的概率分布和预期收益
    """

    def __init__(self):
        """初始化推导引擎"""
        pass

    def infer_probabilities(self, similar_cases):
        """
        从相似案例推导概率分布

        Args:
            similar_cases: list of dicts, each with:
                - case: full case dict
                - outcome: str ('success', 'partial_success', 'failure', 'delisted')
                - similarity_score: float (0-1)
                - duration_months: int

        Returns:
            dict: {
                'success': 0.40,
                'partial_success': 0.40,
                'failure': 0.20,
                'delisted': 0.0,
                'case_count': 5,
                'avg_duration_success': 30,
                'avg_duration_failure': 24
            }
        """
        if not similar_cases:
            return self._default_probabilities()

        # 统计各个结果的出现次数
        outcomes = [case['outcome'] for case in similar_cases]
        outcome_counts = Counter(outcomes)
        total = len(similar_cases)

        # 标准化为 4 个结果
        probabilities = {
            'success': outcome_counts.get('success', 0) / total,
            'partial_success': outcome_counts.get('partial_success', 0) / total,
            'failure': outcome_counts.get('failure', 0) / total,
            'delisted': outcome_counts.get('delisted', 0) / total,
        }

        # 计算各结果的平均周期
        success_durations = [c['duration_months'] for c in similar_cases if c['outcome'] == 'success']
        failure_durations = [c['duration_months'] for c in similar_cases if c['outcome'] in ['failure', 'delisted']]

        result = {
            'success': probabilities['success'],
            'partial_success': probabilities['partial_success'],
            'failure': probabilities['failure'],
            'delisted': probabilities['delisted'],
            'case_count': total,
            'avg_duration_success': np.mean(success_durations) if success_durations else None,
            'avg_duration_failure': np.mean(failure_durations) if failure_durations else None,
        }

        return result

    def infer_stock_price_path(self, similar_cases, current_price):
        """
        从历史案例的股价路径，推导当前股票的预期走势

        Args:
            similar_cases: list of similar case dicts
            current_price: float, 当前股价

        Returns:
            dict: {
                'month_3': 3.5,
                'month_6': 4.2,
                'month_12': 5.5,
                'month_24': 8.0,
                'month_36': 10.0
            }
        """
        if not similar_cases:
            return {}

        # 收集所有相似案例的股价路径
        price_paths = []
        for item in similar_cases:
            case = item['case']
            if case['stock_price_path']:
                try:
                    path = json.loads(case['stock_price_path']) if isinstance(case['stock_price_path'], str) else case['stock_price_path']
                    price_paths.append(path)
                except:
                    pass

        if not price_paths:
            return {}

        # 计算每个时间点的平均倍数（相对于初始价）
        months = ['month_3', 'month_6', 'month_12', 'month_24', 'month_36']
        average_multiples = {}

        for month in months:
            values = [p.get(month, 0) for p in price_paths if p.get(month)]
            if values:
                average_multiples[month] = np.mean(values)

        # 乘以当前股价（进行归一化）
        normalized_path = {}
        for month, multiple in average_multiples.items():
            if multiple > 0:
                # 假设历史案例的初始价都归一化为 1.0，所以 multiple 就是倍数
                normalized_path[month] = current_price * multiple

        return normalized_path

    def infer_average_outcome(self, similar_cases):
        """
        推导平均预期结果

        Args:
            similar_cases: list of similar cases

        Returns:
            dict: {
                'expected_multiple': 3.2,  # 期望倍数
                'expected_return_pct': 220,  # 期望收益率
                'expected_duration_months': 28
            }
        """
        if not similar_cases:
            return {}

        # 加权平均倍数
        multiples = [c['case'].get('multiple_achieved', 1) for c in similar_cases]
        weights = [c['similarity_score'] for c in similar_cases]

        expected_multiple = np.average(multiples, weights=weights) if multiples else 1.0
        expected_return_pct = (expected_multiple - 1) * 100

        # 平均周期
        durations = [c['duration_months'] for c in similar_cases if c['duration_months']]
        expected_duration = np.mean(durations) if durations else 24

        return {
            'expected_multiple': round(expected_multiple, 2),
            'expected_return_pct': round(expected_return_pct, 1),
            'expected_duration_months': int(expected_duration)
        }

    def extract_warning_signals(self, similar_cases):
        """
        从失败案例中提取预警信号

        Args:
            similar_cases: list of similar cases

        Returns:
            dict: {
                'common_failure_signals': [
                    ('重整延期', 4),  # (信号, 出现次数)
                    ('新业务困难', 3),
                ],
                'what_to_watch_for': [
                    '重整延期',
                    '新业务困难'
                ]
            }
        """
        failure_signals = []

        for item in similar_cases:
            case = item['case']
            if case['outcome'] in ['failure', 'delisted', 'partial_success']:
                if case['failure_signals']:
                    try:
                        signals = json.loads(case['failure_signals']) if isinstance(case['failure_signals'], str) else case['failure_signals']
                        if isinstance(signals, list):
                            failure_signals.extend(signals)
                    except:
                        pass

        signal_counts = Counter(failure_signals)
        most_common = signal_counts.most_common(5)

        return {
            'common_failure_signals': most_common,
            'what_to_watch_for': [signal[0] for signal in most_common],
            'based_on_cases': len(failure_signals)
        }

    def extract_success_factors(self, similar_cases):
        """
        从成功案例中提取成功要素

        Args:
            similar_cases: list of similar cases

        Returns:
            dict: {
                'common_success_factors': [
                    ('新业务质量优秀', 2),
                    ('国资注入充足', 2),
                ],
                'success_keys': [
                    '新业务质量优秀',
                    '国资注入充足'
                ]
            }
        """
        success_factors = []

        for item in similar_cases:
            case = item['case']
            if case['outcome'] == 'success':
                if case['success_factors']:
                    try:
                        factors = json.loads(case['success_factors']) if isinstance(case['success_factors'], str) else case['success_factors']
                        if isinstance(factors, list):
                            success_factors.extend(factors)
                    except:
                        pass

        factor_counts = Counter(success_factors)
        most_common = factor_counts.most_common(5)

        return {
            'common_success_factors': most_common,
            'success_keys': [factor[0] for factor in most_common],
            'based_on_cases': len(success_factors)
        }

    @staticmethod
    def _default_probabilities():
        """默认概率（当没有相似案例时）"""
        return {
            'success': 0.3,
            'partial_success': 0.3,
            'failure': 0.3,
            'delisted': 0.1,
            'case_count': 0,
            'avg_duration_success': None,
            'avg_duration_failure': None,
        }


# ══════════════════════════════════════════════════
# 测试代码
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    print("【概率推导引擎测试】\n")

    # 模拟相似案例
    mock_similar_cases = [
        {
            'case': {
                'case_name': '*ST云网',
                'outcome': 'success',
                'multiple_achieved': 8.0,
                'stock_price_path': '{"month_3": 1.5, "month_6": 2.0, "month_12": 3.5, "month_24": 6.0, "month_36": 8.0}',
                'success_factors': '["新业务落地", "国资充足"]',
                'failure_signals': '[]'
            },
            'outcome': 'success',
            'duration_months': 36,
            'similarity_score': 0.85
        },
        {
            'case': {
                'case_name': '*ST盐湖',
                'outcome': 'success',
                'multiple_achieved': 8.3,
                'stock_price_path': '{"month_3": 1.3, "month_6": 1.8, "month_12": 3.0, "month_24": 6.5, "month_36": 8.3}',
                'success_factors': '["行业利好", "新业务质量"]',
                'failure_signals': '[]'
            },
            'outcome': 'success',
            'duration_months': 30,
            'similarity_score': 0.78
        },
        {
            'case': {
                'case_name': '*ST辅仁',
                'outcome': 'delisted',
                'multiple_achieved': 0.5,
                'stock_price_path': '{"month_3": 0.8, "month_6": 0.6}',
                'success_factors': '[]',
                'failure_signals': '["重整延期", "新业务无着落"]'
            },
            'outcome': 'delisted',
            'duration_months': 24,
            'similarity_score': 0.72
        }
    ]

    # 初始化推导引擎
    inferencer = ProbabilityInferencer()

    # 推导概率
    probs = inferencer.infer_probabilities(mock_similar_cases)
    print("概率分布:")
    print(json.dumps(probs, indent=2))
    print()

    # 推导股价路径
    price_path = inferencer.infer_stock_price_path(mock_similar_cases, current_price=3.0)
    print("预期股价路径 (当前股价 ¥3.0):")
    print(json.dumps(price_path, indent=2))
    print()

    # 推导平均结果
    avg_outcome = inferencer.infer_average_outcome(mock_similar_cases)
    print("平均预期结果:")
    print(json.dumps(avg_outcome, indent=2))
    print()

    # 提取预警信号
    warning_signals = inferencer.extract_warning_signals(mock_similar_cases)
    print("预警信号:")
    print(json.dumps(warning_signals, indent=2))
