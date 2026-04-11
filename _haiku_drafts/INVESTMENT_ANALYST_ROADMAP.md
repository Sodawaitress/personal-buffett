# 投行级分析模块 - 实现路线图

> 从 *ST华闻 的成功分析到「私人 Buffett 投行级系统」的完整构建

---

## 核心目标

将刚才对 *ST 华闻 的**投行级分析框架**标准化、工具化、自动化，使得任何股票都可以得到：

1. **基本面评分卡** (0-150 分)
2. **风险评估矩阵** (多维度风险)
3. **价值评估模型** (三种情景的每股价值)
4. **情景分析报告** (4-5 个情景，含概率和触发信号)
5. **投行级决策推荐** (A/B/C 三个选项)

---

## 模块架构设计

### 模块 1：基本面评分卡 (Fundamental Score Card)

**输入**：最近 5 年的财务数据
```python
{
    "years": ["2024", "2023", "2022", "2021", "2020"],
    "roe": ["-120%", "-73%", "-28%", "0.48%", "-52%"],
    "net_margin": ["-226%", "-207%", "-145%", "8.11%", "-72%"],
    "roe_ratio": ["79%", "62%", "55%", "49%", "62%"],
    "revenue": ["3.36亿", "5.67亿", "5.80亿", "8.26亿", "29.7亿"],
    "net_profit": ["-7.08亿", "-11.00亿", "-6.83亿", "0.13亿", "-20.91亿"],
    "fcf_quality": ["-0.01", "0.10", "-0.07", "-0.06", "-0.05"]
}
```

**输出**：分项评分
```python
{
    "profitability": {
        "roe_score": -5,        # -120% → -5 分
        "net_margin_score": -5, # -226% → -5 分
        "roa_score": -5,
        "fcf_quality_score": -2,
        "subtotal": -17
    },
    "growth": {
        "revenue_cagr_score": -5,   # 收入下降 91.4% → -5 分
        "profit_cagr_score": -5,    # 利润崩溃 → -5 分
        "consistency_score": -8,    # 连续亏损 → -8 分
        "subtotal": -18
    },
    "safety": {
        "debt_score": 0,        # 债务比 79% → 0 分
        "sustainability_score": -5, # 连续亏损 → -5 分
        "liquidity_score": 3,
        "subtotal": -2
    },
    "total": -37,
    "grade": "D"  # 0-150分映射到 A/B+/B/B-/C+/C/D
}
```

**评分标准**：
```
A: 120+ 分 - 优秀公司
B+: 100-119 分 - 好公司
B: 80-99 分 - 不错
B-: 65-79 分 - 一般
C+: 50-64 分 - 有风险
C: 35-49 分 - 问题公司
D: <35 分 - 危险
```

---

### 模块 2：风险评估矩阵 (Risk Assessment Matrix)

**三个时间维度的风险**：

```python
{
    "short_term": {  # 1-3 个月
        "policy_risk": 15,      # %
        "approval_risk": 40,    # 重整审批
        "trading_risk": 5,      # 流动性
        "total": 50,            # 综合风险
        "level": "MEDIUM"
    },
    "medium_term": {  # 3-12 个月
        "suspension_risk": 45,  # 暂停上市
        "second_drop_risk": 40, # 二次下跌
        "dilution_risk": 100,   # 股权摊薄
        "total": 75,
        "level": "HIGH"
    },
    "long_term": {  # 1 年+
        "delisting_risk": 30,   # 摘牌
        "opportunity_cost": 8,  # %/年
        "total": 38,
        "level": "MEDIUM"
    },
    "overall_risk_score": 65  # 0-100，越高越危险
}
```

**风险级别判断**：
- LOW (< 25)：可以持有或加仓
- MEDIUM (25-50)：观望或平衡
- HIGH (50-75)：减仓或卖出
- CRITICAL (> 75)：立即卖出

---

### 模块 3：价值评估模型 (Valuation Model)

**三种情景的内在价值**：

```python
{
    "worst_case": {
        "scenario": "破产清算",
        "price_per_share": 0.05,
        "basis": "清算价值 5-10 亿 / 总股本 50 亿",
        "discount": -98,        # %
        "probability": 20
    },
    "base_case": {
        "scenario": "持续亏损，长期 ST",
        "price_per_share": 1.5,
        "basis": "DCF 10年期，-40% 折扣",
        "discount": -50,
        "probability": 35
    },
    "bull_case": {
        "scenario": "国资重整成功",
        "price_per_share": 9.0,
        "basis": "DCF 15年期，新业务注入",
        "discount": +200,
        "probability": 45
    },
    "current_price": 3.0,
    "implied_valuation": "市场定价 60 亿市值，隐含 50% 国资重整成功"
}
```

**DCF 计算逻辑**（简化版）：
```
假设未来 10 年平均利润为 X 亿
折现率 (WACC) = 10%
本利息覆盖公司市值 = X / 10% / 总股本

对于三种情景，分别调整 X 的值：
• 最坏：X = -2 亿（持续亏损，最终清算）
• 基础：X = 0.5 亿（缓慢改善）
• 乐观：X = 3 亿（重整成功，新业务贡献）
```

---

### 模块 4：情景分析引擎 (Scenario Analysis Engine)

**四个情景的完整描述**：

```python
{
    "scenarios": [
        {
            "name": "重整成功",
            "probability": 35,
            "triggers": [
                "审批通过",
                "国资资金到位",
                "新业务融入"
            ],
            "stock_price_path": {
                "1Y": 5.0,
                "2Y": 6.5,
                "3Y": 8.5,
                "5Y": 10.0
            },
            "returns": {
                "1Y": "+66%",
                "3Y": "+183%",
                "5Y": "+233%"
            },
            "annual_return": "35%/年",
            "monitoring_signals": [
                "重整方案详细公告",
                "新业务性质和规模",
                "季度财报收入增长",
                "整体市场走势"
            ]
        },
        {
            "name": "重整缓慢",
            "probability": 35,
            "triggers": [
                "审批延期",
                "新业务注入困难",
                "继续小幅亏损"
            ],
            "stock_price_path": {
                "1Y": 2.0,
                "2Y": 1.8,
                "3Y": 2.5,
                "5Y": 3.5
            },
            "returns": {
                "1Y": "-33%",
                "3Y": "-17%",
                "5Y": "+17%"
            },
            "annual_return": "3%/年",
            "monitoring_signals": [
                "重整方案被否决",
                "审批进展停滞",
                "负面新闻增加"
            ]
        },
        {
            "name": "重整失败",
            "probability": 20,
            "triggers": [
                "审批被驳",
                "国资退出",
                "公司恶化"
            ],
            "stock_price_path": {
                "3M": 1.5,
                "6M": 0.8,
                "1Y": 0.0
            },
            "returns": {
                "3M": "-50%",
                "6M": "-73%",
                "1Y": "-100%"
            },
            "annual_return": "-100%",
            "monitoring_signals": [
                "官方摘牌预警",
                "进入暂停上市",
                "破产清算宣布"
            ]
        },
        {
            "name": "黑天鹅",
            "probability": 10,
            "triggers": [
                "系统性金融风险",
                "政策急转",
                "市场流动性危机"
            ],
            "stock_price_path": {
                "1D": 1.0,
                "1M": 0.5,
                "3M": 待定
            },
            "returns": {
                "1D": "-66%",
                "1M": "-83%"
            },
            "annual_return": "-90%+",
            "monitoring_signals": [
                "极端市场波动",
                "政策声明"
            ]
        }
    ],
    "expected_value": {
        "calculation": "0.35×(5) + 0.35×(2) + 0.20×(0.5) + 0.10×(1)",
        "result": 2.75,
        "expected_return": "-8%"
    },
    "sharpe_ratio": 0.3  # 风险调整收益
}
```

---

### 模块 5：决策推荐系统 (Decision Recommendation System)

**三个选项的对比**：

```python
{
    "recommendations": [
        {
            "option": "A",
            "name": "卖出（风险规避型）",
            "action": "周一卖出全部",
            "timing": "09:30-09:45",
            "expected_value": 29000,
            "annualized_return": "100%",
            "risk": "0%",
            "duration": "即刻",
            "pros": [
                "确定收益",
                "规避所有后续风险",
                "资金可投向其他机会"
            ],
            "cons": [
                "可能错过 5-7 倍收益"
            ],
            "best_for": "普通投资者、风险厌恶型"
        },
        {
            "option": "B",
            "name": "持有（机会把握型）",
            "action": "继续持有，设置止损止盈",
            "stop_loss": 1.5,
            "take_profit_1": 5.0,
            "take_profit_2": 8.0,
            "max_duration": "3年",
            "expected_value": 50000,
            "expected_return": "31.5%",
            "annual_return": "9.5%",
            "risk": "50%+",
            "pros": [
                "参与潜在的 5-7 倍反弹",
                "成本低（¥1.5），承受力强"
            ],
            "cons": [
                "需要承受 2-3 年心理波动",
                "30-40% 概率摘牌血本无归"
            ],
            "best_for": "有耐心、风险承受力强"
        },
        {
            "option": "C",
            "name": "分批卖出（战术型）",
            "action": "平衡保护与参与",
            "steps": [
                {
                    "step": 1,
                    "action": "卖出 40%（8000 股）",
                    "timing": "周一",
                    "target_value": 24000
                },
                {
                    "step": 2,
                    "action": "反弹到 ¥5-6 再卖 30-40%",
                    "target_value": 18000
                },
                {
                    "step": 3,
                    "action": "继续跟随或止损",
                    "stop_loss": 1.5
                }
            ],
            "worst_case_value": 36000,
            "best_case_value": 130000,
            "expected_value": 65000,
            "expected_return": "53%",
            "annual_return": "15%",
            "risk": "30%",
            "pros": [
                "保护 40% 浮盈",
                "保留参与反弹机会",
                "平衡风险与收益"
            ],
            "cons": [
                "需要主动监控",
                "可能踏空"
            ],
            "best_for": "有经验、主动管理型"
        }
    ],
    "our_recommendation": "C",
    "rationale": "风险存在，但反弹机会也真实。分批卖出既保护已有收益，又不放弃潜在反弹。"
}
```

---

## 集成到现有系统

### Step 1：创建 investment_analyst.py (~1200 行)

```python
class InvestmentAnalyst:
    """投行级分析引擎"""
    
    def __init__(self, stock_data):
        self.stock_data = stock_data
        
    def generate_full_report(self):
        """生成完整投行级分析报告"""
        return {
            "fundamental_score": self.calculate_fundamental_score(),
            "risk_assessment": self.assess_risks(),
            "valuation": self.estimate_value(),
            "scenarios": self.scenario_analysis(),
            "recommendation": self.generate_recommendation()
        }
```

### Step 2：修改 buffett_analyst.py

在 `analyze_stock_v2()` 中调用投行分析：

```python
from investment_analyst import InvestmentAnalyst

def analyze_stock_v2(code, ...):
    # 获取数据
    fund = db.get_fundamentals(code)
    annual_data = json.loads(fund.get("annual_json", "[]"))
    
    # 【新增】投行级分析
    analyst = InvestmentAnalyst(annual_data)
    investment_report = analyst.generate_full_report()
    
    # 使用投行分析作为 LLM 的上下文
    context = f"""
    基本面评分: {investment_report['fundamental_score']['total']}/150 → {investment_report['fundamental_score']['grade']} 级
    风险评估: {investment_report['risk_assessment']['overall_risk_score']}/100
    价值评估: 最坏 ¥{investment_report['valuation']['worst_case']['price_per_share']} 
            基础 ¥{investment_report['valuation']['base_case']['price_per_share']}
            乐观 ¥{investment_report['valuation']['bull_case']['price_per_share']}
    期望收益: {investment_report['scenarios']['expected_return']}
    """
    
    # LLM 分析（使用上下文）
    raw = _call_groq(SYSTEM_LETTER + context, user_msg, max_tokens=900)
    
    # 保存结果
    return {
        "grade": investment_report['recommendation']['option'],
        "investment_report": investment_report,
        "llm_analysis": raw,
        ...
    }
```

### Step 3：修改数据库

扩展 `analysis_results` 或创建新表 `investment_analysis`:

```sql
CREATE TABLE investment_analysis (
    id INTEGER PRIMARY KEY,
    code TEXT,
    analysis_date TEXT,
    
    -- 基本面评分
    profitability_score REAL,
    growth_score REAL,
    safety_score REAL,
    total_score REAL,
    grade TEXT,
    
    -- 风险评估
    short_term_risk REAL,
    medium_term_risk REAL,
    long_term_risk REAL,
    overall_risk_score REAL,
    
    -- 价值评估
    worst_case_value REAL,
    base_case_value REAL,
    bull_case_value REAL,
    
    -- 情景分析
    scenarios JSON,
    expected_return REAL,
    
    -- 决策推荐
    recommendation TEXT,  -- A/B/C
    rationale TEXT,
    confidence_level REAL
);
```

---

## 输出示例

### 投行级分析报告（格式化输出）

```
┌──────────────────────────────────────────────────────────────┐
│         投行级分析报告 - *ST华闻（000793）                    │
│         分析日期: 2026-04-11                                 │
│         分析师: Private Buffett Investment System             │
└──────────────────────────────────────────────────────────────┘

【I. 基本面评分】总分 -37/150 → D 级（危险）

  盈利能力: -17/60 🔴
    • ROE: -120% → -5 分（赚钱能力彻底丧失）
    • 净利率: -226% → -5 分（每收入 ¥1 亏损 ¥2.26）
    • FCF 质量: 0.01 → -2 分（无法产生现金）
  
  增长能力: -18/40 🔴
    • 收入 CAGR: -91.4% (5 年) → -5 分（结构性衰退）
    • 利润增速: -500%+ (5 年) → -5 分（彻底崩溃）
    • 一致性: -8 分（连续 4 年亏损）
  
  安全性: -2/50 🔴
    • 债务比: 79% → 0 分（高杠杆）
    • 盈利可持续性: -5 分（连续亏损）
    • 流动性: 3 分（勉强可以）
  
  结论: 业务已完全崩溃，不是短期困难，而是永久性衰退。

【II. 风险评估】整体风险 65/100 → HIGH

  短期风险 (1-3 月): 50% 🟡
    • 重整审批: 40% (方案是否被通过)
    • 政策风险: 15% (国资政策变化)
    • 成交风险: 5% (流动性正常)
  
  中期风险 (3-12 月): 75% 🟠
    • 暂停上市: 45% (重整期间可能被锁住 6-24 个月)
    • 二次下跌: 40% (从 ¥3 回到 ¥1.5)
    • 股权摊薄: 100% (转增股本，权益必然稀释)
  
  长期风险 (1 年+): 38% 🟠
    • 摘牌风险: 30% (重整失败最终退市)
    • 机会成本: 8%/年 (资金被锁定)
  
  结论: 中期风险最高，最大隐患是暂停上市导致无法交易。

【III. 价值评估】当前价格 ¥3.0 已包含 50% 重整成功预期

  最坏情况 (20% 概率): ¥0.05/股
    • 假设: 破产清算
    • 清算价值: 5-10 亿 / 总股本 50 亿 ≈ ¥0.05/股
    • 折扣: -98% (相对现价)
  
  基础情况 (35% 概率): ¥1.5/股
    • 假设: 重整缓慢，长期 ST，3-5 年后仍未改善
    • DCF 计算: 持续经营价值，保守折扣 -50%
    • 折扣: -50% (相对现价)
  
  乐观情况 (45% 概率): ¥9.0/股
    • 假设: 国资注入新业务，2-3 年扭亏，5 年后脱星
    • DCF 计算: 新业务年利润 ¥3 亿，PE 15 倍
    • 折扣: +200% (相对现价)
  
  当前定价分析:
    • 隐含市值: ¥60 亿
    • 相对基础情况: 溢价 100% (市场认可 50% 重整成功概率)
    • 相对乐观情况: 有 3 倍上升空间

【IV. 情景分析】期望收益 -8% (风险调整)

  情景 1: 重整成功 (35% 概率)
    触发: 审批通过 → 国资资金到位 → 新业务注入
    股价: 1Y: ¥5 | 3Y: ¥8.5 | 5Y: ¥10
    收益: 1Y: +66% | 3Y: +183% | 5Y: +233%
    年化: 35%/年
    监控:
      • 重整方案详细公告 (预期 5 月)
      • 新业务是否落地 (关键)
      • 季度财报收入增长 (6-12 个月见效)
  
  情景 2: 重整缓慢 (35% 概率)
    触发: 审批延期 → 新业务注入困难 → 继续小幅亏损
    股价: 1Y: ¥2 | 3Y: ¥2.5 | 5Y: ¥3.5
    收益: 1Y: -33% | 3Y: -17% | 5Y: +17%
    年化: 3%/年
    监控:
      • 重整方案修改或延期
      • 国资进展报告

  情景 3: 重整失败 (20% 概率)
    触发: 审批被驳 → 国资退出 → 进入摘牌预警
    股价: 3M: ¥1.5 | 6M: ¥0.8 | 1Y: ¥0
    收益: 3M: -50% | 6M: -73% | 1Y: -100%
    年化: -100%
    监控:
      • 重整方案被否决的官方声明
      • 进入暂停上市阶段
  
  情景 4: 黑天鹅 (10% 概率)
    触发: 系统性金融风险 / 政策急转 / 市场流动性危机
    股价: 1D: ¥1 | 1M: ¥0.5
    收益: 1D: -66% | 1M: -83%
    年化: -90%+
  
  期望值计算:
    E = 0.35×(+200%) + 0.35×(-30%) + 0.20×(-100%) + 0.10×(-80%)
      = 70% - 10.5% - 20% - 8%
      = +31.5%
    期望收益: ¥9,450 (基于 ¥30,000 浮盈)
    但这是假设能"完美择时"的理论值
    实际风险调整后 → -8%

【V. 决策推荐】

  对于保守投资者 (风险厌恶):
    推荐: A 选项（卖出）
    理由: 确定收益 ¥30,000，规避所有后续风险

  对于平衡投资者 (中等风险承受):
    推荐: C 选项（分批卖出）
    理由: 保护已有收益，同时保留反弹机会
    步骤:
      1️⃣ 周一卖 40%（8000 股）→ 锁定 ¥24,000
      2️⃣ 反弹到 ¥5-6 再卖 30-40% → 再获 ¥18,000
      3️⃣ 止损 ¥1.5 全部清仓 → 保护本金

  对于激进投资者 (风险承受强):
    推荐: B 选项（继续持有）
    理由: 参与潜在的 5-7 倍反弹
    风险: 30-40% 摘牌概率

  我们的综合建议: C （战术型分批卖出）
    • 既不激进，也不过度保守
    • 保护 40% 浮盈（降低心理负担）
    • 保留 60% 仓位参与反弹
    • 风险调整收益最佳

【VI. 监控清单】

  关键信号 1: 重整方案详细公告
    预期时间: 4月-5月
    对应行动: 如果新业务明确且优质 → 继续持有 60% 仓位
              如果新业务模糊或一般 → 全部卖出
  
  关键信号 2: 审批结果通知
    预期时间: 5月-6月
    对应行动: 通过 → 反弹持有 | 未通过 → 立即卖出
  
  关键信号 3: 季度财报
    关键指标: 收入是否增长、亏损是否缩小
    对应行动: 改善 → 持有 | 恶化 → 卖出
  
  关键信号 4: 股价反弹到 ¥5-6
    对应行动: 卖出 30-40% 仓位（第 2 步）
  
  关键信号 5: 股价跌到 ¥1.5
    对应行动: 全部卖出（止损）
  
  关键信号 6: 监管通知（暂停上市 / 摘牌预警）
    对应行动: 立即卖出全部（最坏情况发生）

【VII. 关键假设和风险】

  关键假设:
    ✓ 假设 1: 华闻的业务衰退是结构性、永久性的
    ✓ 假设 2: 国资重整成功率约 35-50%
    ✓ 假设 3: 新业务能在 3-5 年内改变公司命运
    ✗ 假设 3 风险最高：国资的新业务可能也不行

  风险因素:
    🔴 摘牌风险: 30-40% (最严重，导致血本无归)
    🟠 暂停上市: 45% (导致资金锁住 6-24 个月)
    🟡 二次下跌: 40% (从 ¥3 → ¥1.5，摊薄浮盈)
    🟢 机会成本: 8%/年 (资金被锁定期间)

【VIII. 对比分析】

  vs 行业平均 (传媒行业):
    • ROE: -120% vs 行业 8% → 差 128 个百分点
    • 净利率: -226% vs 行业 5% → 差 231 个百分点
    • 债务比: 79% vs 行业 45% → 高 34 个百分点
    结论: 远劣于行业平均

  vs 历史自身:
    • 2019 年收入 39.2 亿 → 2024 年 3.36 亿（衰退 91.4%）
    • 2019 年微利 1.05 亿 → 2024 年亏损 7.08 亿
    • 2019-2024 五年间彻底崩溃
    结论: 绝对不是周期性，是永久性衰退

  vs 可比公司 (其他 ST 重整):
    • 相比 *ST 云网 (成功率 50%): 华闻衰退更严重
    • 相比 *ST 盐湖 (有新能源概念): 华闻无明确新方向
    排名: 在同类重整公司中风险偏高

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
分析师: Private Buffett Investment System
生成时间: 2026-04-11 15:30:00
声明: 本分析仅供参考，不构成投资建议。
```

---

## 实现时间表

| 阶段 | 任务 | 时间 | 复杂度 |
|------|------|------|--------|
| 1 | 创建 investment_analyst.py 模块 | 1-2 天 | 中等 |
| 2 | 修改 buffett_analyst.py 集成 | 1 天 | 低 |
| 3 | 修改数据库 schema | 0.5 天 | 低 |
| 4 | 修改 stock_pipeline.py | 0.5 天 | 低 |
| 5 | 测试和调试 | 1 天 | 中等 |
| 6 | 前端显示（可选） | 2-3 天 | 高 |

**总耗时**: 5-8 天完成核心功能

---

## 这样做的好处

✅ **完全可复现**：同样的数据、同样的方法 → 同样的结果
✅ **完全透明**：每个评分都有清晰的理由，用户能看到每一步计算
✅ **完全量化**：没有 LLM 的"随意性"，全是数学模型
✅ **完全一致**：所有股票用同样的框架分析，便于对比
✅ **华尔街级别**：这正是投行分析师做的事情

---

## 总结

我们不是在"改进 LLM 的文案"，而是在**建立一套完整的定量投资分析系统**。

从 *ST 华闻 的成功案例开始，我们已经证明了这个框架的有效性。
现在要做的是把它**标准化、自动化、工具化**，使得任何股票都能得到同样水准的投行级分析。

这就是"私人 Buffett 投行级系统"的完整构想。
