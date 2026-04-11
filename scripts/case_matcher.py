"""
历史案例匹配引擎 - 可复用框架

这个模块实现了案例相似度计算，用于：
1. 从历史案例库中找出与当前股票相似的案例
2. 为概率推导提供数据基础
3. 在投行分析中展示「历史对标」
"""

import json
import sys
from pathlib import Path

# 添加 stock-radar 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import db


class CaseMatcher:
    """
    案例匹配算法

    核心逻辑：
    1. 提取当前股票的特征（ROE、收入下滑、债务比、行业、事件类型）
    2. 遍历历史案例库，计算相似度
    3. 返回排序后的相似案例列表
    """

    def __init__(self, similarity_threshold=0.6):
        """
        初始化匹配器

        Args:
            similarity_threshold: 相似度阈值（0-1），只返回相似度 > 该值的案例
        """
        self.threshold = similarity_threshold
        self.cases = db.get_all_historical_cases()

    def extract_features(self, stock_data):
        """
        从股票数据中提取特征

        Args:
            stock_data: dict with keys:
                - roe: float (%)
                - net_margin: float (%)
                - revenue_decline_pct: float (%)
                - debt_ratio: float (%)
                - industry: str
                - event_type: str

        Returns:
            dict: 标准化后的特征向量
        """
        return {
            'roe_range': self._categorize_roe(stock_data.get('roe', 0)),
            'revenue_decline': stock_data.get('revenue_decline_pct', 0),
            'debt_level': self._categorize_debt(stock_data.get('debt_ratio', 0)),
            'industry': stock_data.get('industry', 'unknown'),
            'event_type': stock_data.get('event_type', 'unknown')
        }

    def find_similar_cases(self, stock_data):
        """
        找出与当前股票相似的历史案例

        Args:
            stock_data: dict with keys: roe, net_margin, revenue_decline_pct,
                       debt_ratio, industry, event_type

        Returns:
            list: 排序后的相似案例列表
                [
                    {
                        'case': case_dict,
                        'similarity_score': 0.85,
                        'outcome': 'success',
                        'duration_months': 36
                    },
                    ...
                ]
        """
        current_features = self.extract_features(stock_data)
        similar_cases = []

        for case in self.cases:
            score = self._calculate_similarity(current_features, case)
            if score > self.threshold:
                similar_cases.append({
                    'case': case,
                    'similarity_score': score,
                    'outcome': case['outcome'],
                    'duration_months': case['reorganization_duration_months']
                })

        # 按相似度降序排列
        return sorted(similar_cases, key=lambda x: x['similarity_score'], reverse=True)

    def _calculate_similarity(self, current_features, historical_case):
        """
        计算相似度（0-1 之间）

        相似度基于以下维度：
        1. ROE 范围相似（20%权重）
        2. 收入下滑幅度相似（20%权重）
        3. 债务水平相似（20%权重）
        4. 行业相同（20%权重）
        5. 事件类型相同（20%权重）
        """
        score = 0

        # 1. ROE 相似度：两者都负还是都正
        if current_features['roe_range'] == self._categorize_roe(historical_case['initial_roe']):
            score += 0.2

        # 2. 收入下滑幅度相似：差异 < 20% 则得分
        current_decline = current_features['revenue_decline']
        case_decline = historical_case['revenue_decline_pct']
        if abs(current_decline - case_decline) < 20:
            score += 0.2

        # 3. 债务水平相似
        if current_features['debt_level'] == self._categorize_debt(historical_case['initial_debt_ratio']):
            score += 0.2

        # 4. 行业相同
        if current_features['industry'].lower() == (historical_case['industry'] or '').lower():
            score += 0.2

        # 5. 事件类型相同
        if current_features['event_type'].lower() == (historical_case['event_type'] or '').lower():
            score += 0.2

        return score

    @staticmethod
    def _categorize_roe(roe):
        """将 ROE 分类为离散级别"""
        if roe is None:
            return 'unknown'
        if roe < -50:
            return 'severe_negative'
        elif roe < -10:
            return 'moderate_negative'
        elif roe < 0:
            return 'slight_negative'
        elif roe < 5:
            return 'low_positive'
        elif roe < 15:
            return 'moderate_positive'
        else:
            return 'high_positive'

    @staticmethod
    def _categorize_debt(debt_ratio):
        """将债务比分类为离散级别"""
        if debt_ratio is None:
            return 'unknown'
        if debt_ratio > 80:
            return 'extreme_high'
        elif debt_ratio > 60:
            return 'high'
        elif debt_ratio > 40:
            return 'moderate'
        else:
            return 'low'


# ══════════════════════════════════════════════════
# 测试代码
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    print("【案例匹配引擎测试】\n")

    # 初始化匹配器
    matcher = CaseMatcher(similarity_threshold=0.6)
    print(f"✓ 加载了 {len(matcher.cases)} 个历史案例\n")

    # 模拟当前股票数据（*ST华闻 示例）
    st_huawen_data = {
        'roe': -120,
        'net_margin': -85,
        'revenue_decline_pct': 91.4,
        'debt_ratio': 79,
        'industry': 'Media',
        'event_type': 'reorganization'
    }

    print("当前股票特征：")
    features = matcher.extract_features(st_huawen_data)
    print(json.dumps(features, indent=2))
    print()

    # 查找相似案例
    similar = matcher.find_similar_cases(st_huawen_data)
    print(f"找到 {len(similar)} 个相似案例（相似度 > 0.6）:\n")

    for i, item in enumerate(similar, 1):
        case = item['case']
        print(f"{i}. {case['case_name']} - 相似度 {item['similarity_score']:.1%}")
        print(f"   结果: {item['outcome'].upper()}")
        print(f"   时长: {item['duration_months']} 个月")
        print()
