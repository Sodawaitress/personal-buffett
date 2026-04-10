# 📖 定量化评级系统使用指南

## 快速开始

### 1. 基础用法（最简单）

```python
from scripts.quantitative_rating import QuantitativeRater

# 创建评级引擎
rater = QuantitativeRater()

# 调用评级（假设你已经从数据库读取了数据）
result = rater.rate_stock(
    code="600031",                    # 股票代码
    name="三一重工",                  # 股票名称
    annual_data=[                     # 财务数据，从新到旧
        {
            "year": "2025",
            "roe": "20.5%",
            "net_margin": "12.3%",
            "debt_ratio": "45.0%",
            "net_profit": "50亿",
            "eps": "1.50",
            "ocf_per_share": "2.0",
            "bvps": "10.0"
        },
        {
            "year": "2024",
            "roe": "19.8%",
            # ... 更多数据
        },
        # ... 更多年份
    ],
    pe_percentile=65,                 # PE百分位（0-100，0=最便宜 100=最贵）
    pb_percentile=55,                 # PB百分位
    price_52week_pct=72,              # 52周价格位置（0=年低 100=年高）
    news_signals={}                   # 新闻信号（可选）
)

# 获取结果
print(f"评级: {result['grade']} 级 - {result['conclusion']}")
print(f"得分: {result['score']}/100")
print(f"原因: {result['reasoning']}")
```

---

## 详细参数说明

### annual_data（必需）
财务数据列表，**从最新年份到最老年份**排列。

**格式**：
```python
[
    {
        "year": "2025",
        "roe": "20.5%",           # ROE（股东权益回报率）
        "net_margin": "12.3%",    # 净利率
        "gross_margin": "45.0%",  # 毛利率（可选）
        "debt_ratio": "45.0%",    # 债务比（总负债/总权益）
        "net_profit": "50亿",     # 净利润（单位可以是亿/万/百万）
        "eps": "1.50",            # 每股收益
        "ocf_per_share": "2.0",   # 每股营运现金流
        "bvps": "10.0"            # 每股净资产
    },
    # ... 更多年份
]
```

**来源**：从数据库的 `stock_fundamentals` 表的 `annual_json` 字段读取。

### pe_percentile（可选）
PE 在最近 5 年的百分位数。

- `0-20` = 便宜（底部）
- `40-60` = 平价（中位数）
- `80-100` = 贵（顶部）

如果没有历史数据，用 `None`。

### pb_percentile（可选）
PB 在最近 5 年的百分位数。同上。

### price_52week_pct（可选）
52周价格位置（0-100）。

- `0-10` = 接近年低（买入机会）
- `50` = 中等
- `90-100` = 接近年高（风险）

### news_signals（可选）
新闻信号字典，用来评估管理层。

```python
news_signals = {
    "high_pos_buyback": 1,        # 有回购信号
    "mid_pos_dividend": 0,        # 有分红信号
    "high_neg_resignation": 0,    # CEO/CFO 离职
    "mid_neg_reduction": 0,       # 管理层减持
    "fund_flow_ratio": -2.5       # 资金流向比例
}
```

如果没有，传空字典 `{}`。

---

## 返回结果详解

```python
result = {
    "code": "600031",
    "name": "三一重工",
    "score": 72,                  # 综合得分（0-100）
    "grade": "B",                 # 评级（A / B+ / B / B- / C+ / C / D）
    "conclusion": "持有",         # 建议（买入 / 持有 / 观察 / 减持 / 卖出）
    "emoji": "🟡",               # 视觉标记
    
    "components": {               # 四个维度的详细打分
        "moat": (29, [            # 护城河: 29/40 分
            "ROE: 10/15 分 - 良好盈利能力",
            "净利率: 4/10 分 - 弱定价权",
            # ...
        ]),
        "growth_management": (20, [  # 增长与管理层: 20/25 分
            "利润增长: 8/12 分 - 良好增长",
            # ...
        ]),
        "safety": (16, [          # 安全性: 16/20 分
            "负债风险: 6/10 分 - 中等风险",
            # ...
        ]),
        "valuation": (4, [        # 估值: 4/15 分
            "PE 估值: 1/7 分 - 略贵",
            # ...
        ]),
    },
    
    "red_flags": [                # 风险旗子
        "🚨 ROE < 5%：赚钱能力几乎为零",
        "🚨 连续亏损",
    ],
    
    "reasoning": "综合评分 72/100：不错的公司 + 合理价格",
    "timestamp": "2026-04-10 21:15"
}
```

---

## 评级含义

| 得分 | 评级 | 建议 | 含义 |
|------|------|------|------|
| 85-100 | A | 买入 | 优秀公司 + 便宜价格 |
| 75-84 | B+ | 买入 | 不错的公司 + 合理价格 |
| 65-74 | B | 持有 | 一般公司 + 平价 |
| 55-64 | B- | 持有 | 一般公司，需观察 |
| 45-54 | C+ | 观察 | 有风险，不建议介入 |
| 35-44 | C | 减持 | 问题公司，应减仓 |
| 0-34 | D | 卖出 | 极度风险，立即卖出 |

---

## 实际集成例子

### 从数据库读取数据并评级

```python
from scripts.quantitative_rating import QuantitativeRater
import db
import json

# 初始化
rater = QuantitativeRater()
db.init_db()

# 读取某股票的财务数据
code = "600031"
fund = db.get_fundamentals(code)

# 解析年度数据
annual_data = json.loads(fund.get("annual_json", "[]"))

# 读取估值数据
pe_pct = fund.get("pe_percentile_5y")
pb_pct = fund.get("pb_percentile_5y")

# 如果有价格数据，计算52周位置
price_data = db.get_latest_price(code)
price_52w_pct = calculate_52week_position(price_data)  # 自己实现

# 读取新闻信号
news_signals = extract_news_signals(code)  # 自己实现

# 评级
result = rater.rate_stock(
    code=code,
    name="三一重工",
    annual_data=annual_data,
    pe_percentile=pe_pct,
    pb_percentile=pb_pct,
    price_52week_pct=price_52w_pct,
    news_signals=news_signals
)

# 保存到数据库
db.save_analysis(
    code=code,
    period="daily",
    analysis_date=result["timestamp"][:10],
    grade=result["grade"],
    conclusion=result["conclusion"],
    reasoning=result["reasoning"],
    moat="",  # 可选：保存维度信息
    management="",
    valuation="",
    raw_output=json.dumps(result)  # 保存完整结果
)
```

---

## 各维度详解

### 1️⃣ 护城河 (40 分)

**ROE 评分（15分）**：
- > 25% → 15 分（超强）
- > 20% → 13 分
- > 15% → 10 分
- > 10% → 7 分
- > 5% → 3 分
- 0-5% → **⚠️ 0 分**（赚钱能力几乎为零）
- < 0% → **🚨 -5 分**（亏损）

**净利率评分（10分）**：
- > 25% → 10 分（极强定价权，如茅台）
- > 15% → 8 分
- > 10% → 6 分
- > 5% → 4 分
- 0-5% → 2 分
- < 0% → **🚨 -5 分**（公司在烧钱）

**ROE 稳定性（10分）**：
- 波动 < 10% → 10 分（非常稳定）
- 波动 10-20% → 8 分
- 波动 20-30% → 5 分
- 波动 30-50% → 3 分
- 波动 > 50% → **⚠️ -3 分**（剧烈波动）

**现金流质量（5分）**：
- FCF > 1.0x → 5 分（利润100%转化为现金）
- FCF 0.8-1.0x → 4 分
- FCF 0.5-0.8x → 2 分
- FCF < 0.5x → **⚠️ -2 分**

### 2️⃣ 增长与管理层 (25 分)

**利润增长（12分）**：基于3年CAGR
- CAGR > 30% → 12 分
- CAGR > 15% → 10 分
- CAGR > 10% → 8 分
- CAGR > 5% → 5 分
- 0 < CAGR < 5% → 2 分
- CAGR < 0% → **🚨 -5 分**

**利润一致性（8分）**：过去3年
- 3年都盈利 → 8 分
- 1年亏损 → 5 分
- 2年亏损 → 1 分
- 3年都亏损 → **🚨 -5 分**

**管理层（5分）**：基于新闻信号
- 有回购 → +2 分
- 有分红 → +1 分
- CEO/CFO 离职 → -2 分
- 管理层减持 → -1 分

### 3️⃣ 安全性 (20 分)

**负债风险（10分）**：
- D/E < 0.3 → 10 分（低风险）
- D/E 0.3-0.5 → 8 分
- D/E 0.5-0.8 → 6 分
- D/E 0.8-1.0 → 4 分
- D/E 1.0-2.0 → 2 分
- D/E > 2.0 → **🚨 -5 分**（极度高杠杆）

**盈利可持续性（10分）**：
- 连续3年盈利 → 10 分
- 2年盈利 → 6 分
- 1年盈利 → 2 分
- 连续亏损 → **🚨 -5 分**

### 4️⃣ 估值 (15 分)

**PE 百分位（7分）**：
- 0-20% → 7 分（便宜）
- 20-40% → 5 分
- 40-60% → 3 分（平价）
- 60-80% → 1 分
- 80-100% → **⚠️ -2 分**（贵）

**PB 百分位（5分）**：
- 0-20% → 5 分
- 20-40% → 4 分
- 40-60% → 2 分
- 60-80% → 1 分
- 80-100% → -1 分

**52周价格位置（3分）**：
- 0-10% → 3 分（年低，买入机会）
- 10-20% → 2 分
- 20-80% → 1 分
- 80-90% → 0 分
- 90-100% → **🚨 -3 分**（年高，买入风险）

---

## 测试代码

在 Python 交互式环境中：

```python
>>> from scripts.quantitative_rating import QuantitativeRater
>>> rater = QuantitativeRater()
>>> 
>>> # 测试数据（中国平安）
>>> test_data = [
...     {"year": "2025", "roe": "19.70%", "net_margin": "9.75%", "debt_ratio": "61.17%", "net_profit": "439.45亿", "eps": "5.8000", "ocf_per_share": "7.02", "bvps": "29.38"},
...     {"year": "2024", "roe": "21.29%", "net_margin": "9.52%", "debt_ratio": "62.33%", "net_profit": "385.37亿", "eps": "5.4400", "ocf_per_share": "7.90", "bvps": "28.31"},
... ]
>>> 
>>> result = rater.rate_stock("000333", "中国平安", test_data, 65, 55, 72, {})
>>> print(f"评级: {result['grade']} - {result['conclusion']}")
评级: B - 持有
>>> print(f"得分: {result['score']}/100")
得分: 69/100
```

---

## 常见问题

### Q: 如果数据缺失怎么办？
**A**: 系统有 fallback 机制，会用默认值（通常是中等分）。比如缺少FCF数据，会给3分而不是报错。

### Q: 可以调整权重吗？
**A**: 可以！修改 `quantitative_rating.py` 中各个 `score_*` 函数的返回值就行。比如想让ROE更重要，把15分改成20分。

### Q: 能和现有的 LLM 评级混用吗？
**A**: 可以！这个系统完全独立，不会改动现有的 `buffett_analyst.py`。你可以同时保留两个系统。

### Q: 怎么快速测试所有股票？

```python
from scripts.quantitative_rating import QuantitativeRater
import db
import json

rater = QuantitativeRater()
db.init_db()

# 读取所有自选股
for code in db.get_all_codes():
    fund = db.get_fundamentals(code)
    annual_data = json.loads(fund.get("annual_json", "[]"))
    
    result = rater.rate_stock(
        code=code,
        name="",
        annual_data=annual_data,
        pe_percentile=fund.get("pe_percentile_5y"),
        pb_percentile=fund.get("pb_percentile_5y"),
        price_52week_pct=None,
        news_signals={}
    )
    
    print(f"{code}: {result['grade']} {result['score']}/100 - {result['conclusion']}")
```

---

## 下一步

1. **测试数据** - 用真实股票数据测试，看评级是否合理
2. **调整权重** - 根据测试结果微调各维度的权重
3. **集成到管道** - 在 `stock_pipeline.py` 中调用这个系统替换 LLM
4. **对标历史** - 对比新旧评级，确保连贯性

需要我帮你做这些吗？
