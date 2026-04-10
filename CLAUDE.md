# 私人巴菲特 · Claude Code 工作手册

> 每次新会话开始前读这个文件。不确定做什么就回来看。

---

## 项目定位

个人投资研究助手。用巴菲特++框架分析用户自选股，同时提供被动市场信息流。
详细产品设计见 `PRODUCT.md`，以该文档为准，不擅自改设计。

---

## 当前实现阶段

### ✅ 已完成
- Flask 基础框架（app.py）
- 用户登录/注册（邮箱+密码 + Google OAuth）
- 基础 DB（db.py，待重建）
- NZ 股票数据爬取（nz_fetch.py）
- A 股数据爬取（scripts/stock_fetch.py）
- 宏观数据爬取（scripts/macro_fetch.py）
- 巴菲特分析模型 v1（scripts/buffett_analyst.py）
- NYT 风格 UI 基础（templates/ + static/style.css）
- 周/月/季度 digest（scripts/periodic_digest.py）
- launchd 定时任务（daily）
- US-12 批量选股分析（watchlist.html 多选 + 批量操作栏）
- US-13 我的选股页（/watchlist）
- US-14 首页精简（历史报告移至 /report，首页只留低调入口）
- US-18 首页题头重设计（有持仓紧凑题头 HTML + CSS）
- US-19 视觉分层（新闻区 .news-section-wrap 灰底 CSS）
- US-20 导航栏精简（base.html：只留「我的选股」+ 语言 + 头像下拉）
- US-21 NZ 新闻修复（NZ Herald/Interest/RBNZ 均挂，换 RNZ Business + Stuff）
- US-22 详情页导航（stock.html 面包屑：← 品牌名 + ← 全部选股）
- US-23 公司价值档案页（/stock/<code>/fundamentals：评级时间线 + 财务指标 + 资金流图表 + 护城河）
- 巴菲特信 prompt 升级（GREAT/GOOD/GRUESOME框架 + 护城河方向 + 机构惰性识别 + 数据诚实）
- BUFFETT_PROFILES 全面升级（每只股票加 biz_type + 净利率趋势 + 护城河方向描述）
- US-28 我的选股页重设计（210px 侧边栏 + 快捷操作 + 缩略图模式 + 客户端排序/筛选）
- FCF质量修复（annual 数据补全11个字段）
- ROIC/Owner Earnings/留存利润检验（Sina balance sheet + 预计算方向标签）
- 护城河方向自动判断（ROE/净利率趋势算法）
- LLM ROIC方向错误修复（预计算 ↑/↓ 标签注入 prompt）
- 亏损公司PE估值修复（ROE<0时替换PE显示，改用PB+警告文本）
- US-24 预测追踪（backfill_returns.py + /report/accuracy + launchd daily 17:00 NZT）
- US-25 源代码保护（.env.example 重写 + requirements.txt 补 yfinance + README.md 英文）
- US-26 About 页（/about 无需登录 + 英文 + 项目背景/贡献/技术栈）
- US-29 Pipeline 超时保护（可取消后台 job）
- US-30 我的选股侧边栏重设计（目录式导航 + 过滤 + Popover 操作）
- US-31 我的选股：搜索 + 视图切换 + 选择模式（复选框按需出现，点分析进入选择模式，整卡片可点击）
- US-32 股票详情页重设计（删侧边栏，评级/数据融入头部，Tab 全宽）
- US-33 三段式自选股（持有/观察/卖出）+ 算账页（/watchlist/performance）
- US-34 行为经济学分析（Kahneman 损失厌恶/沉没成本/锚定/FOMO，ST股检测，预计算提示）
- US-40 技术支撑位 + 机构成本参考（MA20/60/120/250 + 60/120日VWAP，新浪K线，fundamentals页Price Ladder展示，注入巴菲特信）
- US-37 持仓成本注入分析（entry_price + buy_date → analyze_stock_v2，pipeline查user_watchlist，浮盈/亏自动更新behavioral_hint）
- Bug fix: 主力资金 NoneType 错误（`.SS` 判断改为 `pure.startswith("6","9")`）
- Bug fix: 601083 锦江航运卡住 6+ 个月（Job 134 在投行信号超时后未继续 AI 分析→手动标记为 failed，新建 Job 135 成功完成→详见 FIX_601083_STUCK_ANALYSIS.md）
- Bug fix: 英文股票新闻为空（yfinance v1.2.0+ 改变 API 结构→修复 pipeline.py 第 92-131 行以支持新 API 嵌套格式→详见 FIX_YFINANCE_NEWS_EMPTY.md）
- 新闻情绪分析升级（_score_news 添加 sentiment 计算与数据库持久化；LLM prompt 增强指示 LLM 必须参考新闻做护城河/管理层判断；新闻显示添加情绪emoji标签 📈/📉/➖）
- Bug fix: 机构持仓季度计算错误（4月传"20263"未来季度→改为正确的"20254"；quarter逻辑按月份判断最近完整季）
- Bug fix: A股价格缺失（_fetch_price 对 market=cn 改用 Sina hq.sinajs.cn，000333/000793/688981/688102 已补价格）
- Bug fix: fundamentals页ROE/净利率/负债率/FCF全为"积累中"（app.py补传annual/pe_current等，模板改用真实数据）
- UX fix: fundamentals护城河假进度条→改用moat_direction标签+reasoning文本；财务指标增加6年历年趋势对比表
- US-41 交互体验修复（首页卡片整体可点击进详情；去掉首页"详情"/"移除"按钮；选择模式加"全选/取消全选"toggle）
- US-43 价值档案并入详情页 Tab（stock.html 新增 tab-fundamentals；stock_page 路由合并数据查询；/fundamentals 重定向；Chart.js 懒加载）
- US-42 个性化首页日报（portfolio_analysis 表；db.get/save_portfolio_brief；scripts/portfolio_brief.py LLM合成；_compute_alert 规则引擎；/api/generate-brief 端点；index.html 今日简报区块 + generateBrief() JS；style.css .daily-brief 样式）
- US-44 首页三卡片「影院感」重设计（垂直堆叠全宽；左边彩色竖条；横排左文右数据布局；今日简报大字体；我的选股右侧显示总数；搜索框内嵌添加卡片）

### ❌ UI 待做（暂停，转数据/模型方向）
- US-07 组合分析 /portfolio（无路由，较大功能）
- US-15 新闻情境化（标注影响哪只持仓）
- US-16 Watchlist 缩略图模式
- US-17 巴菲特++雷达图

### 🔄 下一阶段重点：数据质量 + 模型准确性
（详见用户需求：更准确、有参考性、有前瞻性）

**数据层待补强：**
- 财务指标实时拉取：AKShare stock_financial_abstract_ths 拿 ROE/净利率/资产负债率（现在全是 NULL）
- 机构持仓变动：ak.stock_institute_hold / 大股东增减持公告
- 估值历史：PE/PB 历史百分位（现在只有即时值，没有历史对比）
- 北向资金：盘中运行才有数据，需调整 launchd 时间

**模型层待补强：**
- 巴菲特信已升级 prompt（GREAT/GOOD/GRUESOME + 数据诚实）
- 待做：留存利润检验自动化（5年市值增加 ÷ 5年留存利润）
- 待做：Owner Earnings 估算（需要资本开支数据）
- 待做：护城河方向自动判断（对比 ROE/净利率多期趋势，自动判断 widening/narrowing）
- 第一版暂不做推送，先把分析功能跑通

---

## 关键设计决策（不要改）

| 决策 | 内容 |
|------|------|
| 「巴菲特信」| 分析结果以信件格式呈现，LLM 实时生成，不用模板拼接 |
| 「巴菲特怎么看」| 添加股票按钮的文案，保持这个 |
| 模糊搜索 | AKShare（A股）+ yfinance（其他）双引擎并行 |
| 推送 | Discord（周宇）+ Bear · 妈妈推送 → 第二版 PWA Web Push |
| 角色 | admin（周宇全功能）/ subscriber（妈妈只收推送）|
| DB | 第一版 SQLite，结构兼容未来迁移 PostgreSQL |
| ML | Phase 1 字段第一版埋好（feat_* 列），模型后续做 |
| 侧边栏 | 桌面默认展开，移动端默认收起 |
| 刷新按钮 | 只更新宏观数据（15秒），不重跑 LLM 分析 |

---

## 工作流程（重要，每次都要遵守）

**遇到新需求或新问题时，必须先写 User Story，再动代码。**

流程：
1. 用户提出需求或发现问题
2. 在 `PRODUCT.md` 里写/更新对应 US（含 Acceptance Criteria）
3. 用户确认 US 后，再开始实现
4. 实现完成后，更新 CLAUDE.md 的「已完成」列表

**不允许**：跳过 US 直接写代码，即使需求看起来很小。

---

## 代码规范

- 改文件前必须先 Read，用 Edit 局部修改，**不用 Write 整体覆盖**
- 新功能写进 PRODUCT.md 对应 US 再实现，不擅自加功能
- 每个 User Story 确认后才实现
- 硬编码股票数据（BUFFETT_PROFILES、NZ_PROFILES）逐步迁移到 DB，不新增硬编码
- LLM 调用走 Groq API（groq_client），30 RPM 限制，注意加 sleep

---

## Git 版本管理与质量防护

### 关键功能版本标记

功能表现满意时，打标签备份：
```bash
git tag -a "feature-good-YYYY-MM-DD" -m "质量评分: X/10"
```

质量下降时对比差异：
```bash
git diff feature-good-YYYY-MM-DD..HEAD -- file.py
```

### 修改规范

一个逻辑 = 一个提交。禁止混合多个无关改动。

修改关键功能（搜索、分析、信件）时：
- [ ] 修改前检查是否有现成标签版本
- [ ] 运行对应的测试（`python3 tests/test_*.py`）
- [ ] 手工验证功能正常
- [ ] 一个提交对应一个逻辑改动

### 防退化测试

搜索功能：`python3 tests/test_search.py`

跑通所有检查后才提交。

---

## 市场覆盖与数据完整性

### 支持的股票市场

| 市场 | 代码 | 财务数据 | 完整分析 | 例子 |
|------|------|--------|--------|------|
| A股 | CN | ✅ | ✅ 完整 | 600519（茅台） |
| 美股 | US | ⚠️ 基础 | ⚠️ 部分 | INTC（英特尔） |
| 港股 | HK | ⚠️ 基础 | ⚠️ 部分 | 0700.HK（腾讯） |
| NZ股 | NZ | ⚠️ 基础 | ⚠️ 部分 | CYM.NZ（Countdown） |

**⚠️ 重要**：非 A股股票缺少高级财务数据（ROIC、技术支撑位、信号分析）。

### 添加新股票前检查

1. 确认市场代码（CN/US/HK/NZ）
2. 检查 `scripts/pipeline.py` 中 `_fetch_financials` 是否支持该市场
3. 如不支持，需先补充数据源再添加股票

### 数据缺失处理

页面上显示"数据不足，无法评估"时，说明 pipeline 该步骤被跳过了。不是数据爬取失败，是功能范围限制。

---

## 项目结构

```
stock-radar/
├── CLAUDE.md          ← 你现在在读的文件
├── PRODUCT.md         ← 产品设计文档（以此为准）
├── app.py             ← Flask 主应用
├── db.py              ← 数据库操作
├── scripts/
│   ├── config.py          CN_TZ, BUFFETT_PROFILES（迁移中）
│   ├── stock_fetch.py     A股数据爬取
│   ├── stock_pipeline.py  主 pipeline
│   ├── nz_fetch.py        NZ数据爬取
│   ├── nz_profiles.py     NZ股票资料（迁移中）
│   ├── macro_fetch.py     宏观数据
│   ├── buffett_analyst.py 分析模型
│   └── periodic_digest.py 周/月/季报
├── templates/
│   ├── base.html
│   ├── index.html
│   └── ...
└── static/
    └── style.css
```

---

## 环境

- Python 3.14，命令用 `python3`
- Flask 跑在 port 5001
- DB 文件：`data/radar.db`
- 启动：`python3 app.py`
- 日志：`/tmp/flask-radar.log`
- launchd plist：`~/Library/LaunchAgents/stock.radar.*.plist`

---

## 巴菲特信 · System Prompt 要点

LLM 生成信件时的核心指令：
- 第一人称，巴菲特口吻（朴实、直接、有立场、偶尔幽默）
- 开头用一个类比或小故事引入，不直接讲数字
- 中段讲护城河、估值、资金，用普通人能懂的语言
- 结尾给明确结论：买入/持有/减持/卖出 + 评级
- 提到查理芒格（增加真实感）
- 结尾署名「沃伦·巴菲特（私人版）」
- 附注：数据日期 + 免责声明 + 详情页链接
