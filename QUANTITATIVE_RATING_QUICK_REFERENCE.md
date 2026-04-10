# ⚡ 快速参考卡 - 定量评级系统

## 你现在有 3 种用法

### 方式 1️⃣：命令行（最快）

```bash
# 评级单只股票
cd /Users/poluovoila/.claude/skills/stock-radar
python3 scripts/quantitative_rating_example.py --code 600031

# 评级所有自选股
python3 scripts/quantitative_rating_example.py --all

# 评级所有自选股并保存到数据库
python3 scripts/quantitative_rating_example.py --all --save
```

---

### 方式 2️⃣：Python 代码（最灵活）

```python
from scripts.quantitative_rating import QuantitativeRater

rater = QuantitativeRater()

result = rater.rate_stock(
    code="600031",
    name="三一重工",
    annual_data=[
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
        # ... 更多年份
    ],
    pe_percentile=65,
    pb_percentile=55,
    price_52week_pct=72,
    news_signals={}
)

print(f"评级: {result['grade']} - {result['conclusion']}")
print(f"得分: {result['score']}/100")
```

---

### 方式 3️⃣：从数据库读取（完整流程）

```python
import db
import json
from scripts.quantitative_rating import QuantitativeRater

db.init_db()
rater = QuantitativeRater()

# 读取股票数据
fund = db.get_fundamentals("600031")
annual_data = json.loads(fund.get("annual_json", "[]"))

# 评级
result = rater.rate_stock(
    code="600031",
    name="三一重工",
    annual_data=annual_data,
    pe_percentile=fund.get("pe_percentile_5y"),
    pb_percentile=fund.get("pb_percentile_5y"),
    price_52week_pct=None,
    news_signals={}
)

# 保存到数据库
db.save_analysis(
    code="600031",
    period="daily",
    analysis_date="2026-04-10",
    grade=result['grade'],
    conclusion=result['conclusion'],
    reasoning=result['reasoning'],
    letter_html=json.dumps(result)
)
```

---

## 返回结果快查

```python
result = {
    "score": 66,              # 0-100 综合得分
    "grade": "B",             # A/B+/B/B-/C+/C/D
    "conclusion": "持有",     # 买入/持有/观察/减持/卖出
    "reasoning": "...",       # 评级原因
    
    "components": {
        "moat": (19, [...]),              # 护城河: 分数/40
        "growth_management": (22, [...]), # 增长: 分数/25
        "safety": (18, [...]),            # 安全: 分数/20
        "valuation": (7, [...]),          # 估值: 分数/15
    },
    
    "red_flags": [            # 风险列表
        "🚨 ROE < 5%：...",
        "🚨 连续亏损：...",
    ]
}
```

---

## 评级速查表

| 得分 | 评级 | 意思 |
|------|------|------|
| 85+ | A | 🟢 买入 - 优秀 + 便宜 |
| 75-84 | B+ | 🟢 买入 - 不错 + 合理 |
| 65-74 | B | 🟡 持有 - 一般 + 平价 |
| 55-64 | B- | 🟡 持有 - 一般 + 需观察 |
| 45-54 | C+ | 🟠 观察 - 有风险 |
| 35-44 | C | 🔴 减持 - 问题公司 |
| 0-34 | D | 🔴 卖出 - 极端风险 |

---

## 四维度权重

```
40分: 护城河 (ROE、净利率、稳定性、现金流)
25分: 增长与管理层 (CAGR、一致性、资本配置)
20分: 安全性 (负债、盈利可持续性)
15分: 估值 (PE、PB、52周位置)
───────
100分: 总分
```

---

## 常用命令速查

```bash
# 评级单只股票，查看详细信息
python3 scripts/quantitative_rating_example.py --code 600031

# 评级全部，看排名
python3 scripts/quantitative_rating_example.py --all

# 评级全部并保存到数据库
python3 scripts/quantitative_rating_example.py --all --save

# 运行自带的测试
python3 scripts/quantitative_rating.py
```

---

## 数据字段最小要求

```python
# 最少需要这些字段
annual_data = [
    {
        "year": "2025",          # 必需
        "roe": "20.5%",          # 必需
        "net_margin": "12.3%",   # 必需
        "debt_ratio": "45.0%",   # 必需
        "net_profit": "50亿",    # 必需（用于计算增长）
        # 可选：
        "eps": "1.50",
        "ocf_per_share": "2.0",  # 用于计算FCF质量
        "bvps": "10.0",
    }
]

# 最少需要这些参数
rater.rate_stock(
    code="600031",           # 必需
    name="三一重工",         # 必需
    annual_data=data,        # 必需
    pe_percentile=None,      # 可选，无则默认
    pb_percentile=None,      # 可选
    price_52week_pct=None,   # 可选
    news_signals={}          # 可选
)
```

---

## 红旗指示器

系统会自动标记这些风险：

```
🚨 ROE < 5%                  → 赚钱能力几乎为零
🚨 ROE < 0%                  → 公司亏损
🚨 净利率 < 0%               → 公司在烧钱
🚨 债务比 > 2.0              → 极度高杠杆
🚨 52周位置 > 90%            → 接近年高，买入风险
🚨 连续3年亏损               → 破产风险
🚨 CEO/CFO 离职              → 管理层信号警惕
🚨 主力资金大幅流出          → 机构在离场
```

---

## 实际例子

**中国平安（000333）**

```
综合得分: 69/100 → 🟡 B 级 - 持有

【维度分析】
护城河: 29/40 ✓
  - ROE 19.7% → 良好（10/15）
  - 净利率 9.75% → 弱定价权（4/10）
  - ROE稳定性 → 非常稳定（10/10）
  - FCF 质量 → 优秀（5/5）

增长: 20/25 ✓
  - CAGR 14.2% → 良好增长（8/12）
  - 连续3年盈利（8/8）
  - 有回购信号（4/5）

安全: 16/20 ✓
  - 债务比 61% → 中等风险（6/10）
  - 3年都盈利 → 很好（10/10）

估值: 4/15 ⚠️
  - PE 百分位 65% → 略贵（1/7）
  - PB 百分位 55% → 平价（2/5）
  - 52周位置 72% → 中等（1/3）

【建议】
当前不是最佳介入点。建议等待 PE 回到 60% 以下。
```

---

## 还需要帮助？

- 📖 详细文档：`QUANTITATIVE_RATING_USAGE.md`
- 💻 系统代码：`scripts/quantitative_rating.py`
- 📊 设计文档：`QUANTITATIVE_RATING_SYSTEM.md`
- 🧪 完整例子：`scripts/quantitative_rating_example.py`
