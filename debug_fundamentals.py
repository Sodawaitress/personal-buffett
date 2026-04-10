#!/usr/bin/env python3
"""
诊断脚本：检查非A股的价值档案为什么显示为空

用法: python3 debug_fundamentals.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import db
from datetime import datetime, timezone, timedelta

print("=" * 60)
print("非A股价值档案诊断")
print("=" * 60)

db.init_db()

# 测试 INTC
code = "INTC"
print(f"\n【测试股票】{code}")

stock = db.get_stock(code)
if not stock:
    print(f"❌ 股票未找到")
    sys.exit(1)

print(f"  市场: {stock.get('market')}")

# 获取原始数据
fund = db.get_fundamentals(code)
signals_raw = fund.get("signals", {}) if fund else {}
annual_raw = fund.get("annual", []) if fund else []

print(f"\n【原始数据库数据】")
print(f"  signals: {len(signals_raw)} 字段")
print(f"  annual: {len(annual_raw)} 条记录")

# 显示 signals 的关键字段
print(f"\n【signals 字段内容】")
for key in ['roe', 'profit_margin', 'debt_to_equity', 'year']:
    val = signals_raw.get(key)
    print(f"  {key}: {val} (type: {type(val).__name__})")

# 现在模拟 app.py 的转换
print(f"\n【模拟 app.py 的转换】")

analysis = db.get_latest_analysis(code, period="daily")
signals = signals_raw.copy()
annual = annual_raw.copy()

print(f"  触发条件检查:")
print(f"    signals 非空: {bool(signals)}")
print(f"    annual 为空: {len(annual) == 0}")

if signals and not annual:
    print(f"  ✓ 进入转换块")

    # 执行转换
    if "roe" in signals and isinstance(signals["roe"], (int, float)):
        signals["roe"] = f"{signals['roe']*100:.1f}%"
    if "profit_margin" in signals and isinstance(signals["profit_margin"], (int, float)):
        signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
        signals["profit_margin"] = signals["net_margin"]
    if "debt_to_equity" in signals and isinstance(signals["debt_to_equity"], (int, float)):
        signals["debt_ratio"] = f"{signals['debt_to_equity']:.1f}"

    if analysis and "analysis_date" in analysis:
        signals["year"] = analysis["analysis_date"][:4]
    else:
        CN_TZ = timezone(timedelta(hours=8))
        signals["year"] = datetime.now(CN_TZ).strftime("%Y")

    virtual_annual = {
        "year": signals.get("year", "—"),
        "roe": signals.get("roe", "—"),
        "net_margin": signals.get("net_margin", "—"),
        "debt_ratio": signals.get("debt_ratio", "—"),
        "profit_growth": "—",
    }
    annual = [virtual_annual]

    print(f"\n  【转换后的结果】")
    print(f"    signals.roe: {signals.get('roe')}")
    print(f"    signals.net_margin: {signals.get('net_margin')}")
    print(f"    signals.debt_ratio: {signals.get('debt_ratio')}")
    print(f"    annual: {annual}")
else:
    print(f"  ✗ 未进入转换块")

# 模拟模板逻辑
print(f"\n【模拟模板逻辑】")

lat = annual[0] if annual else None
print(f"  lat = annual[0] if annual else None")
print(f"  → lat = {lat}")

if not lat and signals:
    print(f"  if not lat and signals:")
    print(f"    会设置 lat = signals (但我们已经有 lat 了，所以跳过)")
else:
    print(f"  if not lat and signals:")
    print(f"    条件为 False - lat 已经有值")

print(f"\n【最终结果 (模板会显示)】")
if lat:
    print(f"  ✓ ROE: {lat.get('roe', '—')}")
    print(f"  ✓ Net Margin: {lat.get('net_margin', '—')}")
    print(f"  ✓ Debt Ratio: {lat.get('debt_ratio', '—')}")
else:
    print(f"  ✗ lat 为空，无法显示任何内容")

print(f"\n" + "=" * 60)

# 对比 A 股
print(f"\n【对比】A股数据结构:")

cn_stocks = []
with db.get_conn() as c:
    rows = c.execute("SELECT code, name FROM stocks WHERE market='cn' LIMIT 1").fetchall()
    cn_stocks = rows

if cn_stocks:
    cn_code, cn_name = cn_stocks[0]
    cn_fund = db.get_fundamentals(cn_code)
    cn_annual = cn_fund.get("annual", []) if cn_fund else []

    print(f"  {cn_code} ({cn_name}):")
    print(f"    annual: {len(cn_annual)} 条记录")
    if cn_annual:
        print(f"    years: {[a.get('year') for a in cn_annual[:3]]}")
        print(f"    annual[0]: {cn_annual[0]}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
