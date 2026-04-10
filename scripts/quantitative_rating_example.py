#!/usr/bin/env python3
"""
实际使用示例：从数据库读取股票，用定量评级系统分析，保存结果
"""

import sys
import os

# 添加父目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db
import json
from datetime import datetime
from quantitative_rating import QuantitativeRater


def rate_single_stock(code: str) -> dict:
    """
    对单只股票进行定量评级

    Args:
        code: 股票代码

    Returns:
        评级结果字典
    """

    # 初始化
    db.init_db()
    rater = QuantitativeRater()

    # 从数据库读取股票基本信息
    stock = db.get_stock(code)
    if not stock:
        print(f"❌ 股票 {code} 不存在")
        return {}

    name = stock.get("name", "")
    print(f"\n📊 分析 {name}（{code}）...")

    # 读取财务数据
    fund = db.get_fundamentals(code)
    if not fund:
        print(f"  ⚠️ 无财务数据")
        return {}

    # 解析年度数据
    try:
        annual_data = json.loads(fund.get("annual_json", "[]"))
        if not annual_data:
            print(f"  ⚠️ 年度数据为空")
            return {}
    except:
        print(f"  ⚠️ 年度数据格式错误")
        return {}

    # 获取估值数据
    pe_percentile = fund.get("pe_percentile_5y")
    pb_percentile = fund.get("pb_percentile_5y")

    # 如果需要，这里可以读取新闻信号和价格位置
    # 暂时用空值和默认值
    news_signals = {}
    price_52week_pct = None

    # 进行评级
    result = rater.rate_stock(
        code=code,
        name=name,
        annual_data=annual_data,
        pe_percentile=pe_percentile,
        pb_percentile=pb_percentile,
        price_52week_pct=price_52week_pct,
        news_signals=news_signals
    )

    # 打印结果
    if result:
        print(f"  ✅ 评级: {result['emoji']} {result['grade']} 级 - {result['conclusion']}")
        print(f"     得分: {result['score']}/100")
        print(f"     原因: {result['reasoning']}")

        # 打印维度详情
        print(f"     护城河: {result['components']['moat'][0]}/40")
        print(f"     增长: {result['components']['growth_management'][0]}/25")
        print(f"     安全: {result['components']['safety'][0]}/20")
        print(f"     估值: {result['components']['valuation'][0]}/15")

        if result['red_flags']:
            print(f"     风险: {result['red_flags'][0]}")

    return result


def rate_all_stocks() -> list:
    """
    对所有自选股进行评级
    """
    db.init_db()

    # 读取所有自选股
    watchlist = db.get_user_watchlist(session_user_id=None)  # 如果需要用户ID，改这里

    results = []
    for stock in watchlist:
        code = stock.get("code", "")
        result = rate_single_stock(code)
        if result:
            results.append(result)

    print(f"\n{'='*60}")
    print(f"评级完成：共 {len(results)} 只股票")
    print(f"{'='*60}")

    # 按得分排序（从高到低）
    results_sorted = sorted(results, key=lambda x: x['score'], reverse=True)

    print("\n【按评级排序】")
    for r in results_sorted:
        print(f"{r['emoji']} {r['code']} {r['name']:8} {r['grade']:3} {r['score']:3}/100 - {r['conclusion']}")

    return results


def save_ratings_to_db(results: list):
    """
    将评级结果保存到数据库
    """
    db.init_db()

    today = datetime.now().strftime("%Y-%m-%d")
    saved = 0

    for result in results:
        try:
            db.save_analysis(
                code=result['code'],
                period="daily",
                analysis_date=today,
                grade=result['grade'],
                conclusion=result['conclusion'],
                reasoning=result['reasoning'][:200],  # 截断到200字
                moat=result['components']['moat'][1][0] if result['components']['moat'][1] else "",
                management=result['components']['growth_management'][1][0] if result['components']['growth_management'][1] else "",
                valuation=result['components']['valuation'][1][0] if result['components']['valuation'][1] else "",
                fund_flow_summary="",
                behavioral="",
                tbtf="",
                macro_sensitivity="",
                letter_html=json.dumps(result, ensure_ascii=False),  # 保存完整结果
                raw_output=""
            )
            saved += 1
        except Exception as e:
            print(f"  ⚠️ {result['code']} 保存失败: {e}")

    print(f"\n✅ 已保存 {saved} 条评级到数据库")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="定量评级系统")
    parser.add_argument("--code", help="单只股票代码（如 600031）")
    parser.add_argument("--all", action="store_true", help="评级所有自选股")
    parser.add_argument("--save", action="store_true", help="保存到数据库")

    args = parser.parse_args()

    if args.code:
        # 评级单只股票
        result = rate_single_stock(args.code)
        if args.save and result:
            save_ratings_to_db([result])

    elif args.all:
        # 评级所有股票
        results = rate_all_stocks()
        if args.save:
            save_ratings_to_db(results)

    else:
        print("用法:")
        print("  python3 quantitative_rating_example.py --code 600031        # 评级单只股票")
        print("  python3 quantitative_rating_example.py --all               # 评级所有自选股")
        print("  python3 quantitative_rating_example.py --all --save        # 评级并保存到数据库")
