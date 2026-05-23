# 私人巴菲特 · Claude Daily Routine

每日自动运行，完成两项任务：
1. **Run 1**：给妈妈生成每日股票信号推送（微信 Server酱）
2. **Run 2**：对比网站机械分析 vs Claude 判断，输出改进建议

---

## 配置

```
网站地址: https://personal-buffett.fly.dev
API 端点: /api/claude-summary?token=k69ajOff279kV7Q31Yg6OhZi1hJfwnv0nQa4N6u3AtU&user_id=2
Server酱 Key: SCT333151TD7CBhTlIUVmcP8DwTASclXFK
妈妈的 user_id: 2
```

---

## Run 1 · 妈妈的每日推送

### Step 1：拉取数据

用 WebFetch 或 Bash 调用：
```
GET https://personal-buffett.fly.dev/api/claude-summary?token=k69ajOff279kV7Q31Yg6OhZi1hJfwnv0nQa4N6u3AtU&user_id=2
```

### Step 2：分析逻辑

对每只股票，按以下优先级判断是否值得今日推送：

**必推（满足任意一条）：**
- is_new = true（新加股票，做入门鉴定）
- precursor.survey.days_since_latest ≤ 3 且 事件中有"现场参观"或"特定对象调研"
- precursor.survey.events 中单次 n_inst ≥ 50 且 days_since_latest ≤ 7
- precursor.short_selling.change_pct 绝对值 > 20%（融券大幅变化）

**可推（满足2条以上）：**
- precursor.score ≥ 3
- precursor.survey.count_30d ≥ 3（连续多次调研）
- analysis.grade 上升（对比历史）
- recent_news 中 sentiment > 0.5 且有正面关键词

**不推：**
- precursor 为 null 或 cache_age_hours > 72
- 30天内无任何调研记录
- analysis.grade = "D" 或 "E"（除非有逆转信号）

### Step 3：对每只选中股票，做真正的分析

不要只转述数据。要思考：
- 这家公司是做什么的？现在处于行业周期哪个位置？
- 这次机构调研说明什么？（为什么会来，来了这么多家）
- 估值合理吗？（PE/PB + 历史位置）
- 对妈妈来说，现在应该怎么对待这只股票？

**重要原则：**
- 如果调研方式是"业绩说明会"且之后无跟进 → 机构只是例行参加，不算看好
- 如果是"现场参观"或"实地调研" → 机构主动去工厂，是真正的认可信号
- 单次家数大但只有1次 → 数量炸裂但缺乏持续性，需说明
- 多次调研且时间间隔短 → 这是最强信号，机构在持续建仓逻辑

### Step 4：生成推送内容

格式（纯文本，避免 markdown，因为微信渲染问题）：

```
【每日股票动向】{日期}

{如有新股}
◆ 新入库：{股票名} ({代码})
{2-3句公司介绍 + 第一印象判断}
建议：先观察 / 值得研究 / 可以忽略

{主要信号}
◆ {股票名} ({代码})
{1-2句说明机构动向}
{1句说明这意味着什么}
建议持仓用户：{操作建议}

{如今日无信号}
今日自选股无新的机构动向，继续持有观察。

---
数据来源：东方财富机构调研 | 仅供参考
```

### Step 5：发送 Server酱

```bash
curl -X POST "https://sctapi.ftqq.com/SCT333151TD7CBhTlIUVmcP8DwTASclXFK.send" \
  -H "Content-Type: application/json" \
  -d '{"title": "每日股票动向 {日期}", "desp": "{内容}"}'
```

---

## Run 2 · 网站质量对比报告

### Step 1：选取今日重点股票

从 Run 1 的数据中，选取 1-2 只信号最强的股票做深度对比。

### Step 2：Claude 独立判断

对选中的股票，Claude 基于已有数据做独立判断：
- 评级应该是什么？（A/B/C/D/E）
- 最关键的护城河是什么？
- 现在估值位置（便宜/合理/贵）？
- 机构行为与基本面是否一致？

### Step 3：对比网站现有分析

读取 analysis 字段中的：
- grade（网站评级）
- reasoning（分析理由）
- moat（护城河描述）
- letter_text（巴菲特信摘要）

对比 Claude 的判断，找出差异：

差异类型：
- **评级偏差**：Claude 认为 B，网站给 C → 说明原因
- **信息缺失**：网站没有提到机构调研密度
- **行业背景缺失**：网站用通用框架评估了重资产行业，导致误判财务指标
- **数据时效问题**：网站分析基于过期数据

### Step 4：输出改进日志

写入文件 `/Volumes/ZY/StockRadarCodex/PBC/knowledge/improvement_log.md`（追加）：

```markdown
## {日期} · {股票名} ({代码})

**Claude判断**: {评级} — {一句话理由}
**网站当前**: {评级} — {网站理由摘要}

**差异分析**:
{具体说明差在哪里}

**改进建议**:
1. {具体可操作的改进点}
2. {如适用}

---
```

---

## 触发时间

- 交易日 17:30 北京时间（收盘后1.5小时，precursor 数据已更新）
- 节假日跳过（检查 is_trading_day：股票数据无更新则跳过）

## 判断是否交易日

在 /api/claude-summary 返回的数据中，如果所有 stock_prices 的 change_pct 都是 null 或所有 cache_age_hours > 36，说明今天是非交易日，只输出简短提示即可，不做深度分析。
