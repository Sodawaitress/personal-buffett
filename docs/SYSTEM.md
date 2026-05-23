# 私人巴菲特 · 系统架构说明

> 这份文档解释整个系统的每一块在做什么、数据怎么流动、以及它们之间的联系。
> 看完之后你应该能独立判断：某个功能坏了去哪里找，想改某件事从哪里下手。

---

## 一、全局数据流

```
每天 17:30（北京时间）

[Fly.io 服务器]
  └─ precursor scan（扫机构调研/融券/资金）
  └─ daily_digest.py
       ├─ 从 DB 拿所有用户自选股（去重合并）
       ├─ 组装快照 JSON → commit 到 GitHub
       └─ 读 predictions_pending.json → 存入 DB → 清空

          ↓ GitHub 快照更新

[Claude Routine（claude.ai/code 云端）]
  └─ 读快照（GitHub raw URL）
  └─ Run 1：三层框架选五只，写分析 + 预言
       ├─ PUT improvement_log.md → GitHub main
       ├─ PUT daily_push.txt → GitHub main（触发 Actions）
       └─ PUT predictions_pending.json → GitHub main

          ↓ daily_push.txt 更新

[GitHub Actions]
  └─ 读 daily_push.txt → POST 到 Server酱 → 妈妈微信收到

          ↓ 第二天 Fly.io 跑时

[Fly.io]
  └─ _ingest_predictions_from_github()
       └─ predictions_pending.json → signal_predictions 表

[backfill_returns.py（每日定时）]
  └─ 查 signal_predictions 里 10 天前的预言
  └─ 从 stock_prices 算实际涨跌
  └─ 写回 actual_return_10d + correct 字段
```

---

## 二、每个文件/模块是做什么的

### Fly.io 服务器端

| 文件 | 职责 |
|------|------|
| `scripts/daily_digest.py` | 每日主调度：构建快照、提交 GitHub、读入 Routine 预言存库 |
| `scripts/precursor_scan.py` | 扫描所有 A 股：机构调研热度、融券变化、资金参与度 |
| `scripts/backfill_returns.py` | 回填 signal_predictions 表的实际涨跌和预言准确度 |
| `scripts/stock_pipeline.py` | 单只股票完整分析 pipeline（用户点「分析」时触发） |
| `scripts/buffett_analyst.py` | LLM 调用核心：组装 prompt，调 Groq，解析信件 |
| `scripts/buffett_prompts.py` | 所有 system prompt（6 种框架：成长股/银行/周期/生存等） |
| `radar_app/data/core.py` | SQLite 连接 + 所有建表 SQL + ALTER TABLE 迁移 |
| `radar_app/data/market.py` | precursor 缓存的读写（survey/short_selling/score） |
| `radar_app/data/signal_events.py` | 信号事件检测 + 共振算法（首页「今日信号」榜单） |

### GitHub 仓库（Sodawaitress/personal-buffett）

| 路径 | 内容 | 谁写 | 谁读 |
|------|------|------|------|
| `snapshots/daily_snapshot.json` | 全平台自选股快照（价格/评级/信号/新闻） | Fly.io | Claude Routine |
| `knowledge/improvement_log.md` | Routine 每日分析 + 预言验证记录 | Claude Routine | `/daily` 命令、Run 2 |
| `output/daily_push.txt` | 今日五选纯文本（触发微信推送） | Claude Routine | GitHub Actions |
| `output/predictions_pending.json` | 结构化预言（待存库） | Claude Routine | Fly.io 次日读取 |
| `.github/workflows/wechat-push.yml` | 检测 daily_push.txt 变化 → 发 Server酱 | 代码库 | GitHub Actions 平台 |
| `CLAUDE_ROUTINE.md` | Routine 每次跑的完整指令 | 开发者 | Claude Routine |

### 数据库关键表（SQLite，生产在 Fly.io /data/radar.db）

| 表名 | 存什么 | 关键字段 |
|------|------|------|
| `users` | 用户账号 | id, email, role |
| `user_watchlist` | 自选股 | user_id, stock_code, status(watching/holding/sold), buy_price |
| `analysis_results` | 巴菲特分析结果 | code, grade, conclusion, reasoning, quant_score, data_incomplete, feat_* |
| `stock_prices` | 历史价格快照 | code, price, change_pct, fetched_at |
| `stock_news` | 新闻 + 情绪 | code, title, sentiment, published_at |
| `stock_precursor_cache` | 前兆信号缓存 | code, survey_json, short_json, score, age_hours |
| `precursor_history` | 每日前兆快照（90天滚动） | code, date, score, survey_count |
| `signal_predictions` | **预言记录**（训练数据核心） | code, direction, note, signal_snapshot, actual_return_10d, correct |
| `stock_events` | 公司事件（解禁/公告/催化剂） | code, event_type, event_date, source |

---

## 三、预言→验证→训练数据 闭环

这是系统长期价值的核心。每一条预言最终变成一个标注样本：

```
输入特征（signal_snapshot 字段存 JSON）：
  - 前兆分（precursor score）
  - 机构调研次数/质量
  - 融券变化方向
  - 新闻情绪均值
  - PE/PB 历史百分位
  - 主力资金净流入

预测标签：
  - direction: up / down / sideways
  - horizon_days: 10

实际结果（10天后 backfill_returns.py 填入）：
  - actual_return_10d: +8.3%
  - correct: 1（方向对）或 0（方向错）
```

**积累几百条之后，可以训练一个简单分类模型**，输入信号组合，输出「这个信号组合历史上有多大概率涨」。这就是真正的 Buffett 模型雏形。

---

## 四、分析框架路由（公司类型 → 不同 prompt）

不同类型的公司用完全不同的分析框架：

| company_type | 框架 | 适用 |
|------|------|------|
| `growth_tech` | SYSTEM_GROWTH_QUALITY | 科技成长股（天孚、澜起） |
| `bank_insurance` | SYSTEM_BANK_INSURANCE | 银行/保险 |
| `cycle_commodity` | SYSTEM_CYCLE_POSITION | 周期/大宗（三一重工） |
| `dividend_stable` | SYSTEM_DIVIDEND_SAFETY | 高息防御（核电、水电） |
| `distressed` | SYSTEM_SURVIVAL_CHECK | *ST/困境反转 |
| `speculative` | SYSTEM_SPECULATIVE | 创业板高风险 |

`growth_tech` 框架已加入 S 曲线位置判断（天孚 CPO 那次 Routine 指出的问题）。

---

## 五、data_incomplete × 前兆信号 交叉保护

当一只股票同时满足：
1. `data_incomplete = 1`（财务数据拉取失败）
2. `precursor.score > 3`（机构前兆信号活跃）

页面会覆盖评级显示为「?」，提示「机构信号活跃但财务数据缺失，评级无效——请看机构雷达」，避免澜起科技这类「426家机构在抢却显示卖出」的误导。

---

## 六、改进这个系统的入口

| 想改什么 | 去哪里 |
|------|------|
| Routine 分析逻辑/框架 | `CLAUDE_ROUTINE.md` |
| 某类公司的分析 prompt | `scripts/buffett_prompts.py`（找对应 SYSTEM_* 变量） |
| 首页信号榜单逻辑 | `radar_app/data/signal_events.py` |
| 数据库新增字段 | `radar_app/data/core.py` → `new_cols` 列表 |
| 快照包含哪些数据 | `scripts/daily_digest.py` → `_build_snapshot()` |
| 微信推送格式 | `CLAUDE_ROUTINE.md` Step 4 格式模板 |
| 预言存库逻辑 | `scripts/daily_digest.py` → `_ingest_predictions_from_github()` |
| 预言准确度回填 | `scripts/backfill_returns.py` |
