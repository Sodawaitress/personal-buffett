# 🎯 巴菲特定量评级系统 v2.0
## 基于代码既有规则的数据驱动实现

这个系统完全基于 `buffett_analyst.py` 中已经定义的规则，只是把 LLM 推理**替换成数据计算**。

---

## 📐 四维度评分体系 (总分 0-100)

### 1. 护城河评分 (Moat) - 40 分

#### A. ROE（赚钱能力）- 15 分
```python
def score_roe(roe_pct):
    """ROE 是护城河的核心指标"""
    if roe_pct > 25:
        return 15  # 超强竞争优势
    elif roe_pct > 20:
        return 13
    elif roe_pct > 15:
        return 10
    elif roe_pct > 10:
        return 7
    elif roe_pct > 5:
        return 3
    elif roe_pct >= 0:
        return 1   # 赚钱能力几乎为零
    else:
        return -5  # 🚨 亏损
```

**关键规则** (来自 SYSTEM_LETTER):
- ROE < 5% → 红旗："赚钱能力几乎为零"
- ROE < 0% → 严重红旗："公司无法盈利"

#### B. 净利率（定价权）- 10 分
```python
def score_net_margin(margin_pct):
    """净利率反映定价权，高净利率=有品牌价值"""
    if margin_pct > 25:
        return 10  # 极强定价权（如酒、医药）
    elif margin_pct > 15:
        return 8
    elif margin_pct > 10:
        return 6
    elif margin_pct > 5:
        return 4
    elif margin_pct >= 0:
        return 2
    else:
        return -5  # 🚨 "公司在烧钱"
```

**关键规则**:
- 净利率 < 0% → 红旗："公司在烧钱"

#### C. ROE 稳定性（过去5年）- 10 分
```python
def score_roe_stability(roe_list):
    """ROE 越稳定 = 护城河越稳固"""
    if len(roe_list) < 2:
        return 5  # 数据不足
    
    # 计算 ROE 波动性 (系数变异)
    avg = sum(roe_list) / len(roe_list)
    if avg == 0:
        volatility = float('inf')
    else:
        variance = sum((x - avg) ** 2 for x in roe_list) / len(roe_list)
        std_dev = variance ** 0.5
        volatility = std_dev / abs(avg)
    
    if volatility < 0.15:
        return 10  # 非常稳定
    elif volatility < 0.30:
        return 8
    elif volatility < 0.50:
        return 5
    elif volatility < 0.80:
        return 3
    else:
        return 0   # 剧烈波动
```

**关键规则**:
- 波动 < 10% → "护城河稳固"
- 波动 > 50% → "护城河受压"

#### D. 现金流质量（OCF/NP）- 5 分
```python
def score_fcf_quality(fcf_ratio):
    """现金流质量 > 盈利质量"""
    if fcf_ratio >= 1.0:
        return 5   # 利润100%转化为现金
    elif fcf_ratio >= 0.8:
        return 4
    elif fcf_ratio >= 0.5:
        return 2
    else:
        return 0   # 利润质量存疑
```

**护城河小计**: 15 + 10 + 10 + 5 = **40 分**

---

### 2. 管理层与资本配置 (Management) - 25 分

#### A. 资本配置能力 - 12 分
基于信号评分（新闻信号部分已实现）：

```python
def score_capital_allocation(signals_dict):
    """
    巴菲特的资本配置优先级：
    回购 > 分红 > 并购 > 囤现金 > 乱投
    """
    
    score = 5  # 基础分
    
    # 回购信号：最优的资本配置
    if signals_dict.get("buyback"):
        score += 3
    
    # 分红信号：其次
    elif signals_dict.get("dividend"):
        score += 2
    
    # 并购信号：需要看是否创造价值
    if signals_dict.get("acquisition"):
        # 需要额外检查 PE 倍数
        if signals_dict.get("acquisition_pe_reasonable"):
            score += 1
        else:
            score -= 1  # 溢价并购减分
    
    # 负面信号：CEO/CFO 离职、减持
    if signals_dict.get("ceo_left") or signals_dict.get("cfo_left"):
        score -= 3  # 🚨 管理层"警惕"
    
    if signals_dict.get("insider_sold"):
        score -= 2  # 管理层减持
    
    if signals_dict.get("massive_acquisition"):
        score -= 2  # 盲目并购
    
    return max(0, min(12, score))
```

**关键规则** (来自 SYSTEM_DAILY):
- 管理层「可信」：回购/派息、CEO/CFO 稳定
- 管理层「警惕」：CEO/CFO 离职、盲目并购、减持

#### B. 资金流向健康度 - 8 分
```python
def score_fund_flow(fund_flow_dict):
    """
    机构资金流向反映市场专业人士的认可度
    """
    main_ratio = fund_flow_dict.get("main_ratio", 0)  # 主力资金占比
    
    if main_ratio > 3:
        return 8   # 主力资金大幅流入
    elif main_ratio > 0:
        return 6
    elif main_ratio > -3:
        return 4   # 平衡
    elif main_ratio > -5:
        return 2   # 小幅流出
    else:
        return 0   # 大幅流出 → 风险信号
```

**关键规则**:
- 资金「流出」→ "机构在离场"
- 资金「流入」→ "专业机构看好"

**管理层小计**: 12 + 8 + 5 = **25 分**

---

### 3. 财务安全性 (Safety) - 20 分

#### A. 负债风险 - 10 分
```python
def score_debt(debt_to_equity):
    """
    债务比 = 总负债 / 总权益
    巴菲特偏好低杠杆企业
    """
    if debt_to_equity < 0.3:
        return 10  # 保守，很安全
    elif debt_to_equity < 0.5:
        return 8
    elif debt_to_equity < 0.8:
        return 6
    elif debt_to_equity < 1.0:
        return 4
    elif debt_to_equity < 2.0:
        return 2
    elif debt_to_equity < 3.0:
        return 0   # 高风险
    else:
        return -5  # 🚨 极度高杠杆
```

**关键规则** (来自 SYSTEM_LETTER):
- 债务比 > 20（即 D/E > 2.0）→ 红旗："极度高杠杆"

#### B. 盈利可持续性 - 10 分
```python
def score_profitability_sustainability(profit_list, years=3):
    """
    最近 N 年利润是否持续正增长
    连续亏损 = 没有安全边际
    """
    recent = profit_list[-years:]
    
    if all(p > 0 for p in recent):
        return 10  # 连续盈利
    elif sum(1 for p in recent if p > 0) >= len(recent) - 1:
        return 6   # 1年亏损，其余盈利
    elif sum(1 for p in recent if p > 0) >= 1:
        return 3   # 多年亏损
    else:
        return -5  # 持续亏损 → 破产风险
```

**安全小计**: 10 + 10 = **20 分**

---

### 4. 估值 (Valuation) - 15 分

#### A. PE 相对估值 - 7 分
```python
def score_pe_valuation(pe_current, pe_percentile):
    """
    PE 百分位数：当前 PE 在 5 年内的位置
    百分位越低 = 价格越便宜
    """
    if pe_percentile <= 20:
        return 7   # 便宜（买入机会）
    elif pe_percentile <= 40:
        return 5
    elif pe_percentile <= 60:
        return 3   # 平价
    elif pe_percentile <= 80:
        return 1
    else:
        return -3  # 昂贵（风险位置）
```

#### B. PB 相对估值 - 5 分
```python
def score_pb_valuation(pb_current, pb_percentile):
    """
    PB 百分位数：当前 PB 在 5 年内的位置
    """
    if pb_percentile <= 20:
        return 5   # 便宜
    elif pb_percentile <= 40:
        return 4
    elif pb_percentile <= 60:
        return 2   # 平价
    elif pb_percentile <= 80:
        return 1
    else:
        return -2  # 昂贵
```

#### C. 价格位置风险 - 3 分
```python
def score_price_position(price_52week_pct):
    """
    52周价格位置：0% = 年低，100% = 年高
    """
    if price_52week_pct >= 90:
        return -3  # 🚨 接近年高，买入风险大
    elif price_52week_pct >= 80:
        return 0
    elif price_52week_pct <= 10:
        return 3   # 接近年低，买入机会
    elif price_52week_pct <= 20:
        return 2
    else:
        return 1   # 中间位置
```

**估值小计**: 7 + 5 + 3 = **15 分**

---

## 🎯 最终评级转换

```python
def calculate_buffett_grade(score):
    """根据综合得分生成评级和建议"""
    
    if score >= 85:
        return {
            "grade": "A",
            "conclusion": "买入",
            "emoji": "🟢",
            "description": "优秀公司 + 便宜价格，符合巴菲特标准"
        }
    elif score >= 75:
        return {
            "grade": "B+",
            "conclusion": "买入",
            "emoji": "🟢",
            "description": "不错的公司 + 合理价格"
        }
    elif score >= 65:
        return {
            "grade": "B",
            "conclusion": "持有",
            "emoji": "🟡",
            "description": "一般公司 + 平价"
        }
    elif score >= 55:
        return {
            "grade": "B-",
            "conclusion": "持有",
            "emoji": "🟡",
            "description": "一般公司，需要观察"
        }
    elif score >= 45:
        return {
            "grade": "C+",
            "conclusion": "观察",
            "emoji": "🟠",
            "description": "有风险信号，不建议介入"
        }
    elif score >= 35:
        return {
            "grade": "C",
            "conclusion": "减持",
            "emoji": "🔴",
            "description": "问题公司，应减仓"
        }
    else:
        return {
            "grade": "D",
            "conclusion": "卖出",
            "emoji": "🔴",
            "description": "极度风险或亏损，应立即卖出"
        }
```

---

## 🚨 红旗系统 (覆盖所有规则)

```python
def extract_red_flags(data):
    """
    提取影响评级的关键风险
    这些风险不能被好消息掩盖
    """
    flags = []
    
    # ROE 红旗
    if data.get("roe", 0) < 0.05:
        flags.append("🚨 ROE < 5%：赚钱能力几乎为零")
    if data.get("roe", 0) < 0:
        flags.append("🚨 ROE < 0%：公司在亏损")
    
    # 利润红旗
    if data.get("profit_margin", 0) < 0:
        flags.append("🚨 净利率 < 0%：公司在烧钱")
    
    # 债务红旗
    if data.get("debt_to_equity", 0) > 2.0:
        flags.append("🚨 债务比 > 2.0：极度高杠杆")
    
    # 价格位置红旗
    if data.get("price_52week_pct", 0) > 90:
        flags.append("🚨 52周价格位置 > 90%：接近年高，买入风险大")
    
    # 连续亏损
    profit_history = data.get("profit_history", [])
    if profit_history and all(p < 0 for p in profit_history[-3:]):
        flags.append("🚨 连续 3 年亏损：破产风险")
    
    # 管理层风险
    if data.get("ceo_left") or data.get("cfo_left"):
        flags.append("🚨 CEO/CFO 离职：管理层信号警惕")
    
    # 资金大幅流出
    if data.get("fund_flow_ratio", 0) < -5:
        flags.append("🚨 主力资金大幅净流出：机构在离场")
    
    return flags
```

---

## 📊 输出示例

```
【600031 三一重工】

综合得分：72 分 → **B 级 持有**

━━━━ 维度分析 ━━━━
✓ 护城河：32/40 分
  - ROE 20% → 护城河稳固
  - 净利率 12% → 有定价权
  - ROE 波动 < 10% → 非常稳定
  
✓ 管理层：18/25 分
  - 过去1年有回购 → 资本配置理性
  - CEO/CFO 稳定 → 管理层可信
  - 机构资金小幅流出 → 需要观察
  
✓ 安全性：18/20 分
  - 债务比 45% → 保守水平
  - 连续5年盈利 → 很稳定
  
✓ 估值：4/15 分
  - PE 百分位 75% → 相对高估
  - PB 百分位 65% → 平价
  - 52周位置 72% → 中等水平

━━━━ 关键信号 ━━━━
📈 好消息：新项目中标 ¥50 亿，产能扩产计划
📉 风险：PE 相对历史高位，债券收益率诱人

🎯 结论
当前估值不算便宜，但公司基本面稳定。
建议：现在加仓不划算，持有等待 20-25x PE 的机会。
```

---

## 🔧 实现检查清单

- [ ] 从数据库读取 5 年的财务数据
- [ ] 计算 4 个维度得分
- [ ] 提取所有红旗
- [ ] 生成最终评级和文字说明
- [ ] 存入数据库的 `grade`, `conclusion`, `reasoning` 字段
- [ ] 替换现有的 LLM 调用
- [ ] 测试与历史评级的一致性

这个系统完全**透明、可解释、可重现**，就是你要的。
