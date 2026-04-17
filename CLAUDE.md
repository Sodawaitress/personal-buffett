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
- Copilot 协作期（2026-04-08 ~ 04-11，Claude 限额期间）：
  - 定量评级系统（quantitative_rating.py，LLM 失败时纯数据驱动打分）
  - JPMorgan + Google News 新闻源（美股/港股/NZ 替代方案）
  - Groq 超时从 40s 改为 180s（pipeline 层）
  - `get_latest_analysis` 改为 `ORDER BY id DESC`
  - 遗留问题：historical_cases 死代码（db.py 已于 2026-04-13 清除）
- Bug fix: Groq _call_groq 超时不重试（except Exception 吞掉 Timeout→返回空）→ 分离 Timeout 捕获，信件生成 timeout 25s→90s（2026-04-13）
- Bug fix: 评级系统全部输出 C（QuantitativeRater.rate() 方法不存在→改为正确的 rate_stock()，评级由定量分数决定，不再 parse LLM 文本）（2026-04-13）
- db.py 清理：删除 historical_cases 建表 SQL + 5 个死函数（2026-04-13）
- Jupyter 环境搭建（notebooks/ 目录，pandas/matplotlib/scikit-learn，2026-04-13）
- **数据架构重设计（2026-04-13，US-46/48/49/50）：**
  - US-48 数据验证层：`_validate_signals()` pipeline 前置检查，PE>150/ROE>80%/负债率>90% 等异常注入警告，写入 `data_quality_log` 表
  - US-46 公司分类器：`stock_meta` 表（st_status/market_tier/name_history），`scripts/classifier.py`，添加股票时自动分类；000793→distressed/*ST，8611.HK→growth_tech/gem，688xxx→growth_tech/star
  - US-49 股票事件数据层：`stock_events` 表，11种事件类型；详情页"事件"tab + 手动录入表单（admin）；事件摘要注入分析 prompt
  - US-50 分析框架路由：`FRAMEWORK_MAP` 6种框架（event_driven/growth_quality/bank_insurance/cycle_position/dividend_safety/survival_check）；`analyze_stock_v2` 按 company_type 路由 system prompt；`framework_used` 字段存入 analysis_results；头部显示紫色框架标签
- **US-51 多用户推送路由（2026-04-14）**：stock_pipeline.py DB 驱动推送；db.py 加 get_users_with_daily_push/get_user_holdings/get_user_watching/set_stock_status；generate_report(allowed_codes=) 支持按用户过滤；send_serverchan() + build_user_push_content()；pipeline 结束后 per-user 推送
- **US-52 admin.py CLI（2026-04-14）**：users/watchlist/set/add/remove/notify/push-key/test-push 命令，直接操作 SQLite
- **US-53 韩股支持（2026-04-14）**：.KS/.KQ market 检测全链路（app/db/search），MARKET_CURRENCY 加 ₩，KRW currency 映射
- **US-54 英文界面补全（2026-04-14）**：i18n 补全 35 个 watchlist key，watchlist.html 硬编码中文全替换
- **GEM高风险检测（2026-04-13）**：classifier.py speculative 类型；SYSTEM_SPECULATIVE 框架；scheme_risk 事件；stock.html 橙色警告横幅
- **US-57 Server酱 微信推送（2026-04-14）**：send_serverchan() POST 到 sctapi.ftqq.com；build_user_push_content() 紧凑表格格式（持仓表 + 巴菲特 reasoning 摘要 + 今日要闻）；admin.py test-push 命令
- **US-58 北向资金修复（2026-04-14）**：stock_fetch.py fetch_north_bound() 字段全部修正（交易日/资金净流入/板块，百万→亿换算）
- **stock_fetch.py DB 驱动（2026-04-14）**：_load_cn_stocks_from_db() 从 DB 读所有用户 A 股自选股，替代硬编码 WATCHLIST；db.py 加 get_all_cn_watchlist_stocks()；fetch_quotes() 改为接受参数
- **Bug fix: 分析完成打断搜索（2026-04-14）**：watchlist.html pollJob 检测搜索框状态，搜索中时改为顶部横幅提示而非强制 location.reload()
- **US-62 Pipeline 分层重构（2026-04-15）**：Layer 1 拆为 5 子层（1a行情/1b财务/1c1新闻/1c2资金/1c3技术面）；各层独立函数+缓存+错误捕获；`run_quant_only` 改为触发 1a+1c1+1c2+Layer2；修复 `batchAnalyze` 读码顺序 bug；修复列表视图 spinner 缺失；列表视图断点从 768px 改为 480px
- **澳股支持（2026-04-15）**：`.AX` → `au` market 全链路（app.py / db.py / pipeline.py / stock_search.py）；`MARKET_CURRENCY` 加 `"au": "A$"`
- **US-63 新闻+信号 Tab 重设计（2026-04-15）**：stock.html 新闻 tab 顶部加「今日信号」面板（资金信号仅A股/技术信号所有市场/新闻情绪所有市场）；新闻列表下移；`.signal-panel` CSS
- **北向资金存储（2026-04-15）**：`db.save_north_bound` / `get_north_bound`（复用 market_data 表）；`_fetch_north_bound()` 加入 1c2 层（24h缓存）；stock.html 信号面板展示沪深分项
- **US-65 差评预警（2026-04-15）**：连续6次 D/D-（非持有区）触发通知；`user_notifications` 表；`check_poor_rating_streak` / `create_notification` / `snooze_notification` / `dismiss_notification`；watchlist.html 顶部黄色横幅（折叠/展开）；「继续观察60天」snooze + 「移除自选股」两个操作
- **Bug fix 批次（2026-04-16）**：
  - `/api/news/<code>` 返回天数从 3 天修正为 7 天
  - `run_letter_only` 存库时漏存 `trade_block` 字段（已补入 save_analysis 调用）
  - 港股/美股 D/E ratio 误显示为"资产负债率"：标签改为"D/E 比率"，D/E>5 时显示 `⚠` + tooltip；`virtual_annual` dict 同步携带 `debt_ratio_note`
  - ML Phase 1 特征字段从未填充：`_run_layer2` 的 `save_analysis` 调用补填 `feat_sentiment_avg` / `feat_fund_flow_net` / `feat_pe_vs_hist`（`feat_price_momentum` / `feat_fear_greed` 仍为 NULL，待后续补）
  - CLAUDE.md 市场覆盖表补入澳股（AU）和韩股（KR）

### ❌ UI 待做（暂停）
- US-07 组合分析 /portfolio（无路由，较大功能）
- US-15 新闻情境化（标注影响哪只持仓）
- US-16 Watchlist 缩略图模式
- US-17 巴菲特++雷达图

### 🔄 下一阶段（按优先级）

**⚠️ 部分完成 / 有残留 bug（2026-04-16 已修复项见下方）：**
- **US-55 数据三层分离**：`/api/refresh-news/<code>` POST 端点存在且有1小时缓存 ✅；`/api/news/<code>` GET 端点已修正为返回7天数据 ✅（原为3天）；stock.html 「更新新闻」按钮已存在 ✅；「分析」与「更新新闻」已分离 ✅
- **US-56 港股/美股财务补强**：`debt_to_equity` 展示已修——非A股标签改为"D/E比率"，>5时显示 `⚠` + tooltip 说明 ✅；yfinance income_stmt 多年趋势抓取已实现（_fetch_1b_financials 有3年趋势） ✅；LLM prompt 禁 markdown 加粗——**待做**
- **US-59 推送质量门禁**：`_score_report()` 不存在；`data_quality_score` 字段不存在；推送前无质量检查——**待做**
- **US-60 买入区间+止损位 UI**：===TRADE=== 解析已实现 ✅；trade_block 已写入 DB（run_pipeline **结果**） ✅；`run_letter_only` 漏存 trade_block 已修复 ✅；stock.html 「操作参数」卡片已存在 ✅；app.py 路由未把 trade_block 单独传模板（analysis dict 里有，stock.html 直接读 `analysis.trade_block` 可正常工作） ✅
- **ML feat_* 字段从未填充**：`_run_layer2` 的 `save_analysis` 调用已补填 `feat_sentiment_avg` / `feat_fund_flow_net` / `feat_pe_vs_hist` ✅；`feat_price_momentum` 和 `feat_fear_greed` 还是 NULL（需要价格历史和宏观数据，后续再补）

**数据层待补强：**
- 财务指标实时拉取：AKShare stock_financial_abstract_ths 拿 ROE/净利率/资产负债率（现在全是 NULL）
- 机构持仓变动：ak.stock_institute_hold / 大股东增减持公告
- 估值历史：PE/PB 历史百分位（现在只有即时值，没有历史对比）
- 北向资金：需收盘后运行 pipeline 才能验证 signals.north_flow 非 NULL（US-58 最后一项 AC）
- US-59 推送质量门禁（_score_report() 待实现）
- US-56 LLM 禁 markdown 加粗（system prompt 加指令待做）

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
| 澳股 | AU | ⚠️ 基础 | ⚠️ 部分 | BHP.AX（必和必拓） |
| 韩股 | KR | ⚠️ 基础 | ⚠️ 部分 | 005930.KS（三星） |

**⚠️ 重要**：非 A股股票缺少高级财务数据（ROIC、技术支撑位、信号分析）。港股/美股的「资产负债率」字段实为 D/E ratio，已在页面加 ⚠ 标注区分。

### 添加新股票前检查

1. 确认市场代码（CN/US/HK/NZ/AU/KR）
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
