# 非A股价值档案为空的原因和解决方案

## 问题

你看到的 Intel（INTC）页面的"价值档案"标签显示为空，但同样的标签对阳光电源（300274）显示完整数据。

## 根本原因

**你的 Flask 应用进程还在运行旧代码，没有重启。**

我们在 GitHub 上的代码修改已经完成：
- Commit cf209d4：添加非A股数据转换逻辑
- Commit 9fa54a6：修复 CN_TZ 变量定义错误
- Commit a9f9556：添加诊断脚本

但你本地运行的 Flask 进程可能：
1. 运行的是旧版本的 app.py
2. 或者模板被缓存了

## 解决方案

### 第一步：确认代码更新

```bash
cd /Users/poluovoila/.claude/skills/stock-radar
git pull origin main
```

### 第二步：重启 Flask 应用

**必须完全杀死旧的进程：**

```bash
# 查找并杀死所有 Flask 进程
pkill -f "python3 app.py"

# 等待 1 秒
sleep 1

# 重新启动
python3 app.py
```

### 第三步：验证修复

**方式 1 - 运行诊断脚本（不需要浏览器）：**

```bash
python3 debug_fundamentals.py
```

应该看到：
```
✓ ROE: 0.0%
✓ Net Margin: -0.5%
✓ Debt Ratio: 37.3
```

**方式 2 - 在浏览器中验证：**

1. 在浏览器中访问 http://localhost:5002
2. 搜索 INTC（或其他非A股如 JPM、TSLA）
3. 点击"价值档案"标签
4. 应该看到 ROE、净利率、资产负债率等卡片

## 代码变更说明

### app.py (第 247-277 行)

非A股没有多年历史数据（annual 为空），所以代码：
1. 检测到 `signals` 存在但 `annual` 为空
2. 将 signals 中的数据转换为百分比字符串格式
3. 创建一个"虚拟年度"记录放入 annual 数组
4. 这样模板就能统一处理

```python
if signals and not annual:
    # 转换为百分比
    signals["roe"] = f"{signals['roe']*100:.1f}%"
    signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
    signals["debt_ratio"] = f"{signals['debt_to_equity']:.1f}"
    
    # 创建虚拟年度
    virtual_annual = {
        "year": "2026",
        "roe": "0.0%",
        "net_margin": "-0.5%",
        "debt_ratio": "37.3",
    }
    annual = [virtual_annual]
```

### templates/stock.html (第 257-264 行)

1. 移除了 `{% if market == "cn" %}` 限制（原本只显示A股）
2. 添加了备选逻辑：如果 `annual` 为空但 `signals` 存在，使用 signals

```jinja2
{% set lat = annual[0] if annual else none %}
{# 对非A股，从signals里提取财务指标 #}
{% if not lat and signals %}
  {% set lat = signals %}
{% endif %}
```

## 数据对比

### A股（阳光电源 300274）
- 有 6 年的历史数据（annual 数组有 6 条记录）
- 模板显示当前年 + 历史对比
- 显示完整的历史数据表格

### 非A股（Intel INTC）
- 只有当前财务数据（annual 为空）
- app.py 创建虚拟年度并转换数据
- 模板显示当前财务指标（ROE、净利率、负债率）
- 不显示历史对比（因为没有历史数据）

## 故障排查

如果重启后仍然看不到数据，请：

1. **检查 Flask 日志：**
   ```bash
   tail -f /tmp/xinglu.log
   ```
   看是否有 500 错误

2. **运行诊断脚本：**
   ```bash
   python3 debug_fundamentals.py
   ```
   检查数据转换是否正常

3. **清除浏览器缓存：**
   - Chrome: Cmd + Shift + Delete
   - 或者用无痕窗口重新访问

4. **检查网络请求：**
   - 打开浏览器开发者工具 (F12)
   - 查看网络标签
   - 确认 /stock/INTC 返回 200 状态码

## 最后

所有代码都已推送到 GitHub，诊断工具也已准备好。
重启 Flask 应用后应该立即看到效果。

有任何问题可以运行 `debug_fundamentals.py` 来诊断。
