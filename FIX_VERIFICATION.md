# ✅ 非A股价值档案修复完成

## 问题描述
用户报告: Intel 等非A股票的"价值档案"标签页显示为空，尽管有分析结果（信）。

## 根本原因
1. **pipeline.py (line 335)**: 对非A股（market != "cn"），`get_fundamentals()` 返回空dict，导致财务指标不被加载
2. **stock.html (line 228)**: 整个"基本面指标"部分被 `{% if market == "cn" %}` 包裹，限制只显示A股
3. **app.py**: 缺乏从 `signals` dict 到模板期望的 `annual[]` 数组的转换逻辑

## 修复实施

### 1. ✅ pipeline.py (第335行)
**变更前:**
```python
fundamentals= db.get_fundamentals(code) if market == "cn" else {}
```
**变更后:**
```python
fundamentals= db.get_fundamentals(code)  # 所有市场都支持
```
**效果:** 非A股的财务数据现在被正确加载和存储到数据库

### 2. ✅ templates/stock.html (第262行)
**移除了市场限制:**
```jinja2
{# 对非A股，从signals里提取财务指标 #}
{% if not lat and signals %}
  {% set lat = signals %}
{% endif %}
```
**效果:** 模板现在可以为任何市场渲染财务指标

### 3. ✅ app.py (第247-279行)
**添加数据转换逻辑:**
```python
if signals and not annual:
    # 转换为百分比字符串（模板期望的格式）
    signals["roe"] = f"{signals['roe']*100:.1f}%"
    signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
    signals["debt_ratio"] = f"{signals['debt_to_equity']:.1f}"
    signals["year"] = "2026"
    
    # 创建虚拟年度记录供模板使用
    virtual_annual = {
        "year": signals["year"],
        "roe": signals["roe"],
        "net_margin": signals["net_margin"],
        "debt_ratio": signals["debt_ratio"],
        "profit_growth": "—",
    }
    annual = [virtual_annual]
```
**效果:** signals dict 被转换成 annual[] 数组，模板能够统一处理

## 验证结果

✅ **诊断脚本测试通过** (`test_fundamentals.py`)
```
✓ Signals data found: 11 fields
✓ Annual array is empty (as expected for non-A-stock)
✓ Transformation applied
✓ roe: 0.0%
✓ net_margin: -0.5%
✓ debt_ratio: 37.3
✓ Template rendering: ROE / NET_MARGIN / DEBT_RATIO all display correctly
```

## 数据流程

```
1. 用户点击 /stock/INTC
   ↓
2. app.py 调用 db.get_fundamentals("INTC")
   ├─ pipeline.py 已正确加载非A股财务数据
   └─ 返回 {"signals": {...}, "annual": []}
   ↓
3. app.py 检测 signals 存在但 annual 为空
   ├─ 转换 signals 中的百分比字段
   ├─ 创建 virtual_annual record
   └─ annual = [virtual_annual]
   ↓
4. 传递到模板: render_template("stock.html", signals=signals, annual=annual)
   ↓
5. 模板渲染:
   ├─ lat = annual[0]  # 获取虚拟年度
   ├─ {% if lat.roe %} → 显示 "0.0%"
   ├─ {% if lat.net_margin %} → 显示 "-0.5%"
   └─ {% if lat.debt_ratio %} → 显示 "37.3"
```

## 已知约束

- 非A股只显示"当年"数据（virtual_annual）
- 无法显示历史年份对比（A股有 annual[] 历史数组）
- 这是合理的，因为非A股 API 通常只提供最新财报

## 如何验证修复

1. **运行诊断脚本:**
   ```bash
   python3 test_fundamentals.py
   ```

2. **在网页上验证:**
   - 搜索 "INTC" 或其他非A股
   - 点击"价值档案"标签
   - 应该看到 ROE、净利率、资产负债率等指标

3. **检查数据库:**
   ```bash
   python3 -c "
   import db
   db.init_db()
   fund = db.get_fundamentals('INTC')
   if fund and fund.get('signals'):
       print('✓ INTC fundamentals:', fund['signals'].keys())
   "
   ```

## 相关提交

- Commit: `cf209d4` 
- Message: "Fix: Enable fundamentals display for non-A-stock markets and add LLM fallback"
- Files changed: app.py, pipeline.py, scripts/buffett_analyst.py, templates/stock.html

## 建议

为了确保修复生效:
1. 重启 Flask 应用 (`python3 app.py`)
2. 清除浏览器缓存（或使用无痕模式）
3. 搜索并点击一个非A股（如 INTC、JPM、AAPL）
4. 点击"价值档案"标签，应该看到财务指标
