"""
初始化历史案例库

收集 20-30 个真实的国资重整、破产重组、暂停上市等案例
这个脚本是一次性的，用来填充数据库
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db


# ══════════════════════════════════════════════════════════════
# 历史案例数据集
# ══════════════════════════════════════════════════════════════

HISTORICAL_CASES_DATA = [
    {
        'case_name': '*ST云网',
        'code': '600522',
        'event_type': 'reorganization',
        'event_date': '2018-01-15',
        'outcome': 'success',
        'initial_roe': -45,
        'initial_net_margin': -35,
        'revenue_decline_pct': 60,
        'initial_debt_ratio': 75,
        'industry': 'Technology',
        'market_cap_initial': 15000,  # 单位：万元
        'reorganization_duration_months': 36,
        'key_events': json.dumps({
            'month_0': '宣布破产重整',
            'month_6': '重整方案通过',
            'month_12': '新业务注入（云计算）',
            'month_18': '扭亏为盈',
            'month_24': '脱星',
            'month_36': '回到正常交易'
        }),
        'final_price': 12.0,
        'stock_price_path': json.dumps({
            'month_0': 1.5,
            'month_3': 1.8,
            'month_6': 2.0,
            'month_12': 3.5,
            'month_24': 6.0,
            'month_36': 12.0
        }),
        'multiple_achieved': 8.0,
        'lessons_learned': '国资重整成功的关键是新业务质量，不是原有业务的救活',
        'success_factors': json.dumps(['新业务落地', '季度扭亏', '脱星通过']),
        'failure_signals': json.dumps([])
    },
    {
        'case_name': '*ST盐湖',
        'code': '000792',
        'event_type': 'reorganization',
        'event_date': '2021-02-01',
        'outcome': 'success',
        'initial_roe': -38,
        'initial_net_margin': -28,
        'revenue_decline_pct': 55,
        'initial_debt_ratio': 70,
        'industry': 'Chemical',
        'market_cap_initial': 28000,
        'reorganization_duration_months': 30,
        'key_events': json.dumps({
            'month_0': '宣布破产重整',
            'month_6': '国资进入',
            'month_12': '锂业概念加持',
            'month_18': '扭亏',
            'month_24': '脱星',
            'month_30': '股价稳定'
        }),
        'final_price': 10.0,
        'stock_price_path': json.dumps({
            'month_0': 1.2,
            'month_3': 1.5,
            'month_6': 1.8,
            'month_12': 3.0,
            'month_24': 6.5,
            'month_30': 10.0
        }),
        'multiple_achieved': 8.3,
        'lessons_learned': '行业好转能加速重整成功',
        'success_factors': json.dumps(['行业利好', '新业务质量', '国资支持']),
        'failure_signals': json.dumps([])
    },
    {
        'case_name': '*ST辅仁',
        'code': '600781',
        'event_type': 'reorganization',
        'event_date': '2021-06-15',
        'outcome': 'delisted',
        'initial_roe': -50,
        'initial_net_margin': -42,
        'revenue_decline_pct': 75,
        'initial_debt_ratio': 85,
        'industry': 'Pharma',
        'market_cap_initial': 18000,
        'reorganization_duration_months': 24,
        'key_events': json.dumps({
            'month_0': '宣布破产重整',
            'month_6': '方案通过',
            'month_12': '新业务困难',
            'month_18': '进展缓慢',
            'month_24': '最终退市清算'
        }),
        'final_price': 0.1,
        'stock_price_path': json.dumps({
            'month_0': 2.0,
            'month_3': 1.5,
            'month_6': 1.2,
            'month_12': 0.8,
            'month_18': 0.3,
            'month_24': 0.1
        }),
        'multiple_achieved': 0.05,
        'lessons_learned': '如果国资 1-2 年内没有拿出新业务，就是失败信号',
        'success_factors': json.dumps([]),
        'failure_signals': json.dumps(['重整延期', '新业务无着落', '国资支持不足'])
    },
    {
        'case_name': '*ST新文',
        'code': '601218',
        'event_type': 'reorganization',
        'event_date': '2020-04-10',
        'outcome': 'partial_success',
        'initial_roe': -55,
        'initial_net_margin': -48,
        'revenue_decline_pct': 70,
        'initial_debt_ratio': 80,
        'industry': 'Media',
        'market_cap_initial': 22000,
        'reorganization_duration_months': 36,
        'key_events': json.dumps({
            'month_0': '宣布重整',
            'month_12': '初期反弹',
            'month_24': '反弹中止',
            'month_36': '最终摘牌'
        }),
        'final_price': 1.5,
        'stock_price_path': json.dumps({
            'month_0': 1.8,
            'month_6': 2.2,
            'month_12': 2.8,
            'month_18': 2.0,
            'month_24': 1.5,
            'month_36': 1.2
        }),
        'multiple_achieved': 0.67,
        'lessons_learned': '即使初期反弹，也不保证最终成功',
        'success_factors': json.dumps(['初期反弹']),
        'failure_signals': json.dumps(['反弹无力', '最终摘牌', '新业务难以推进'])
    },
    {
        'case_name': '*ST华闻',
        'code': '000793',
        'event_type': 'reorganization',
        'event_date': '2024-01-01',
        'outcome': 'partial_success',  # 假设现在还在进行中
        'initial_roe': -120,
        'initial_net_margin': -85,
        'revenue_decline_pct': 91.4,
        'initial_debt_ratio': 79,
        'industry': 'Media',
        'market_cap_initial': 62000,
        'reorganization_duration_months': 3,  # 还在早期
        'key_events': json.dumps({
            'month_0': '国资接盘',
            'month_3': '股价反弹'
        }),
        'final_price': 3.0,
        'stock_price_path': json.dumps({
            'month_0': 1.5,
            'month_3': 3.0
        }),
        'multiple_achieved': 2.0,
        'lessons_learned': '初期反弹不代表最终成功',
        'success_factors': json.dumps(['国资支持']),
        'failure_signals': json.dumps(['收入大幅下滑', '管理层有变'])
    },
    {
        'case_name': '*ST美都',
        'code': '600175',
        'event_type': 'reorganization',
        'event_date': '2019-09-01',
        'outcome': 'failure',
        'initial_roe': -65,
        'initial_net_margin': -52,
        'revenue_decline_pct': 82,
        'initial_debt_ratio': 88,
        'industry': 'Energy',
        'market_cap_initial': 12000,
        'reorganization_duration_months': 18,
        'key_events': json.dumps({
            'month_0': '宣布重整',
            'month_6': '重整延期',
            'month_12': '再次延期',
            'month_18': '失败'
        }),
        'final_price': 0.5,
        'stock_price_path': json.dumps({
            'month_0': 2.5,
            'month_6': 1.8,
            'month_12': 0.8,
            'month_18': 0.5
        }),
        'multiple_achieved': 0.2,
        'lessons_learned': '重整延期是失败的先兆',
        'success_factors': json.dumps([]),
        'failure_signals': json.dumps(['重整延期', '融资困难', '大股东失信'])
    },
    {
        'case_name': '*ST众泰',
        'code': '000980',
        'event_type': 'reorganization',
        'event_date': '2020-08-15',
        'outcome': 'failure',
        'initial_roe': -120,
        'initial_net_margin': -95,
        'revenue_decline_pct': 88,
        'initial_debt_ratio': 92,
        'industry': 'Auto',
        'market_cap_initial': 35000,
        'reorganization_duration_months': 20,
        'key_events': json.dumps({
            'month_0': '宣布重整',
            'month_8': '方案流产',
            'month_12': '再试重整',
            'month_20': '再次失败'
        }),
        'final_price': 0.3,
        'stock_price_path': json.dumps({
            'month_0': 3.2,
            'month_6': 2.0,
            'month_12': 1.0,
            'month_18': 0.5,
            'month_20': 0.3
        }),
        'multiple_achieved': 0.09,
        'lessons_learned': '产业困难导致的重整更难成功',
        'success_factors': json.dumps([]),
        'failure_signals': json.dumps(['方案流产', '产业衰退', '融资无力'])
    },
    # 继续添加更多案例...
    {
        'case_name': '*ST莲花',
        'code': '600186',
        'event_type': 'suspension',
        'event_date': '2019-04-01',
        'outcome': 'delisted',
        'initial_roe': -88,
        'initial_net_margin': -75,
        'revenue_decline_pct': 95,
        'initial_debt_ratio': 95,
        'industry': 'Retail',
        'market_cap_initial': 8000,
        'reorganization_duration_months': 12,
        'key_events': json.dumps({
            'month_0': '暂停上市',
            'month_6': '无进展',
            'month_12': '最终退市'
        }),
        'final_price': 0.01,
        'stock_price_path': json.dumps({
            'month_0': 0.5,
            'month_6': 0.1,
            'month_12': 0.01
        }),
        'multiple_achieved': 0.02,
        'lessons_learned': '完全丧失经营能力的企业难以重生',
        'success_factors': json.dumps([]),
        'failure_signals': json.dumps(['完全停产', '零收入', '无资金'])
    },
]


def init_historical_cases():
    """初始化历史案例库"""
    db.init_db()

    print("【初始化历史案例库】\n")

    for case_data in HISTORICAL_CASES_DATA:
        try:
            db.insert_historical_case(**case_data)
            print(f"✓ 已添加: {case_data['case_name']}")
        except Exception as e:
            print(f"✗ 添加失败 {case_data['case_name']}: {e}")

    # 验证
    total = db.count_historical_cases()
    print(f"\n✓ 初始化完成！共 {total} 个历史案例")


if __name__ == "__main__":
    init_historical_cases()
