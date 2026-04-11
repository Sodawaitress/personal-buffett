# 待办事项 - 2026-04-11

## 🔴 高优先级

### 1. 数据爬取分层（最重要）
**问题**：每次点"分析"都重新爬所有数据，慢且浪费
**方案**：
- 基本面数据（ROE、财报）→ 每周爬一次，存 `stock_fundamentals.updated_at`
- 新闻/公告 → 每小时爬一次
- 价格/资金流 → 每天爬一次
- AI 分析 → 用现有数据随时跑，不触发爬取
**改动文件**：`pipeline.py`、`db.py`（加 `updated_at` 判断）

### 2. Groq 429 限流处理
**问题**：请求频繁时触发限流，fallback 到定量评级，但用户看到"分析服务暂时不可用"
**方案**：在 `buffett_analyst.py` 加重试+指数退避（等5秒重试，最多3次）
**改动文件**：`scripts/buffett_analyst.py`

### 3. 清理 db.py 里 Haiku 加的 historical_cases
**问题**：Haiku 在 db.py 加了 historical_cases 表和函数，没有被任何地方使用
**位置**：
- 建表语句：211-247行
- 函数：944-999行（`insert_historical_case`、`get_all_historical_cases` 等）
**方案**：删掉这些代码，但保留 SQLite 里已建的表（不影响数据）

## 🟡 中优先级

### 4. 同天分析记录 UPSERT
**问题**：同一天同一股票会有多条分析记录，旧的垃圾记录影响显示
**临时修复**：`get_latest_analysis` 已改为 `ORDER BY id DESC`（今天已修复）
**更好方案**：`save_analysis` 改成同天同股票 UPSERT，或加清理旧记录的逻辑

### 5. 历史案例框架（未完成）
**思路**：找相似历史案例 → 看结果 → 推断当前
**核心原则**：
- 数据从自己的 SQLite 积累，不手动录入
- 给 `analysis_results` 加事件类型字段
- 写相似度查询函数
**注意**：Haiku 写的那套在 `_haiku_drafts/` 里，方向对但数据是假的，不要直接用

## 🟢 低优先级

### 6. 清理 _haiku_drafts
**说明**：`_haiku_drafts/` 里的文件是 Haiku 写的草稿，确认不需要后可删除
**文件列表**：case_matcher.py、probability_inferencer.py、historical_case_integration.py、
init_historical_cases.py、example_usage.py、quantitative_rating_example.py、
HISTORICAL_CASE_FRAMEWORK_IMPLEMENTATION.md、HISTORICAL_CASE_INTEGRATION.md、
INVESTMENT_ANALYST_ROADMAP.md

## ✅ 今天已修复
- Groq 分析超时从 40s 改到 180s
- `get_latest_analysis` 改为按 id DESC 取最新记录
- 清理了 scripts/ 里的 Haiku 草稿文件
- 清理了根目录 Haiku 写的会议报告式 md 文件
