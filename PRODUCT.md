# 私人巴菲特 · Product Design Document
> 确认后再动代码。所有实现细节以本文为准。

---

## 一、产品定位

个人投资研究助手。帮助用户（非专业投资者）用巴菲特框架理解自己持有/关注的股票，同时提供被动的市场信息流，不依赖用户有持仓也能读到有价值的内容。

---

## 二、User Stories

### US-01 · 新用户首次进入

**As a** 新注册用户  
**I want to** 看到一个有内容的首页，即使我还没有添加任何股票  
**So that** 我能立刻感受到产品价值，不是空白页

**Acceptance Criteria:**
- 首页显示两个区域：① 「分析你的股票」空状态卡片 ② 模块化市场信息流（本地 + 国际）
- 「分析你的股票」卡片有醒目的「+ 添加股票」按钮
- 市场信息流内容是系统自动爬取的，与用户是否有持仓无关
- 不显示任何硬编码的股票数据

---

### US-02 · 添加股票（模糊搜索）

**As a** 用户  
**I want to** 用公司名称或股票代码模糊搜索来添加股票  
**So that** 我不需要提前知道准确的 ticker 代码

**Acceptance Criteria:**
- 搜索框输入 "nvidia" / "英伟达" / "NVDA" 均能找到正确结果
- 搜索结果显示：公司名 + 代码 + 交易所 + 当前价格（如可获取）
- 支持市场：NZX、A股（沪深）、港股、美股
- 添加后立即触发该股票的分析 pipeline（见 US-03）
- 侧边栏和主页均可触发添加

---

### US-03 · 添加股票触发分析 pipeline

**As a** 用户  
**I want to** 添加股票后系统，用户点击巴菲特怎么看按钮，自动开始爬取和分析，不需要我手动刷新  
**So that** 我能尽快看到这只股票的分析结果

**Pipeline 步骤（后台异步）：**
1. 爬取基础数据（价格、市值、PE、行业）
2. 爬取近期新闻（30天）
3. 爬取主力资金流向（A股）/ 机构持仓（美股/港股）
4. 运行巴菲特++分析模型，生成结构化分析
5. 保存到 DB，推送通知「分析完成」

**UI 状态：**
- 添加后卡片显示「分析中…」spinner
- 完成后卡片显示一句话简报 + 「查看详情」链接
- 失败显示错误原因 + 重试按钮

---

### US-04 · 首页：有持仓时

**As a** 有持仓的用户  
**I want to** 进入首页直接看到我持有股票的最新分析简报  
**So that** 我每天开始时快速了解自己的投资组合状况

**布局：**
```
[Pulse Bar: NZX50 / Fear&Greed / CNY / A股指数]
[报头: 私人巴菲特 · 日期]
─────────────────────────────────────────────
[我的持仓简报]
  股票卡片1: 名称 | 价格 | 涨跌 | 一句话简报 | 查看详情
  股票卡片2: ...
  [+ 卡片]: 空白卡，中间大加号，点击展开搜索面板
─────────────────────────────────────────────
[市场信息流]
  本地栏 (NZ)          |  国际栏 (A股/全球)
  NZ Herald 文章       |  A股新闻
  RBNZ 声明            |  FOMC / 宏观
  NZX 公告             |  商品 / 汇率解读
```

**Acceptance Criteria:**
- 股票卡片按「最后更新时间」降序排列
- 一句话简报 = 巴菲特++模型输出的第一行结论
- 点击卡片进入该股票的详情页（US-06）
- + 卡片永远显示在持仓卡片列表末尾，只有一个大加号，无其他文字
- 点击 + 卡片 → 卡片网格上方展开搜索面板（只有搜索框，无额外按钮）
- 搜索面板默认隐藏，点 + 后自动 focus 搜索框
- 从下拉结果中选中股票 → 立即自动提交，无需额外点击
- 提交后面板收起，新卡片出现并显示「巴菲特分析中…」

---

### US-05 · 首页：无持仓时

**As a** 没有持仓的新用户  
**I want to** 看到清晰的引导 + 有价值的市场内容  
**So that** 我不会面对空白页离开

**布局：**
```
[Pulse Bar]
[报头]
─────────────────────────────────────────────
[分析你买的股票]  ← 大卡片，占全宽
  「还没有添加股票。搜索添加你关注的公司，我们帮你用巴菲特框架分析。」
  [ 🔍 搜索并添加股票 ]
─────────────────────────────────────────────
[市场信息流] ← 同 US-04 的下半部分
```

---

### US-06 · 股票详情页

**As a** 用户  
**I want to** 点击一只股票后看到完整的分析报告 + 历史数据  
**So that** 我能深入研究某一只股票的投资逻辑

**布局（侧边栏 + 主内容）：**
```
[侧边栏]                    [主内容区]
─ 我的持仓                  [综合分析 / 单股分析 切换]
  · AAPL                   ─ 巴菲特++分析报告
  · 600900.SS              ─ 近期新闻（按相关性排序）
  · FPH.NZ  ← 当前          ─ 历史分析对比（本周/本月/本季）
─ ─ ─ ─ ─ ─                ─ 财务数据摘要
[+ 添加股票]
[删除当前股票]
```

**Tabs / 子页面：**
- **今日简报**：最新一次分析结论
- **新闻**：该股票近30天新闻时间线
- **历史分析**：各期分析对比（周/月/季）
- **数据**：价格历史图、PE、市值、资金流向

---

### US-07 · 投资组合综合分析（Portfolio Analysis）

**As a** 用户  
**I want to** 把我持仓的股票作为一个整体来分析，看组合层面的结论  
**So that** 我能判断整体配置是否合理、风险是否集中、哪里有机会

**页面：** `/portfolio`

**两种入口：**
1. 首页顶部「组合视图」按钮（全部持仓一起分析）
2. 勾选若干张持仓卡片后点「一起分析」（只分析选中的，见 US-12）

**内容分为两层：**

**A. 横向对比表（单只 → 组合视图）**
```
股票        评级   结论         最新价    涨跌   资金流向
NVDA        A     买入         $875     +2.1%  ↑主力流入
三一重工    B+    持有观察     ¥15.2    -0.3%  ↓轻微流出
FPH.NZ      B     合理估值     $22.1    +0.8%  —
```
- 按评级降序排列
- 点击某行跳转单股详情页

**B. 组合级别 LLM 分析（巴菲特怎么看这个组合）**
```
[组合分析信]
你持有的这几只股票中，NVDA 占据 AI 基础设施赛道…
三一重工和 NVDA 之间的宏观关联性较低，有一定分散效果…
整体看：进攻性偏强（A股 + 美科技），建议留意…

结论：组合配置合理，但集中于科技/制造两极，缺乏防御性资产。
```
- 仅在用户手动触发时生成（按钮「让巴菲特看这个组合」）
- LLM 输入：各股最新分析结果 + 持仓比例（如有）
- 不自动运行，避免无谓消耗 API

**Acceptance Criteria:**
- 对比表无需 LLM，实时从 DB 读取
- 组合分析信需手动触发，生成后存入 DB（portfolio_analysis 表）
- 支持「选中几只」进入此页面（与 US-12 联动）

---

### US-13 · 我的选股页（/watchlist）

**As a** 用户
**I want to** 有一个专门管理自选股的页面，可以多选、批量操作
**So that** 首页保持干净的「简报」视角，管理操作有独立空间

**入口：**
- 导航栏加「我的选股」
- 首页持仓简报区右上角加「管理 →」链接

**页面内容（/watchlist）：**
- 完整持仓卡片列表（同首页但带管理功能）
- 右上角「选择」按钮 → 进入多选模式（US-12 逻辑在此）
- 右上角「+ 添加」按钮
- 底部批量操作栏（各自分析 / 组合分析）

**首页持仓区：**
- 保留紧凑卡片（名称 + 价格 + 涨跌 + 一句话结论 + 详情→）
- 不再有「选择」按钮
- 右上角只保留「管理 →」和「+ 添加」

**Acceptance Criteria:**
- 首页持仓区无选择模式
- /watchlist 页包含完整 US-12 多选功能

---

### US-12 · 批量选股分析

**As a** 用户  
**I want to** 在首页勾选几只股票，然后批量触发分析或进入组合分析视图  
**So that** 我能灵活地分析「部分持仓」而不是每次都全选

**UI 交互：**
1. 首页持仓区右上角出现「选择」按钮
2. 点击「选择」后，每张持仓卡片左上角出现 checkbox
3. 勾选 N 张后，底部弹出操作栏：
   ```
   已选 2 只股票    [ 各自重新分析 ]    [ 组合分析 ]    [ 取消 ]
   ```
4. 「各自重新分析」= 依次触发选中股票的 pipeline（A）
5. 「组合分析」= 跳转到 `/portfolio?codes=NVDA,600031` 页面（B）

**Acceptance Criteria:**
- 「各自重新分析」完成后各卡片分别显示 spinner → 结果
- 「组合分析」不需要重新跑 pipeline，直接用 DB 最新数据生成组合视图
- 最少选 1 只，最多选全部

---

### US-08 · 定时自动更新（四种触发模式）

**As a** 用户  
**I want to** 系统按照不同的节奏自动爬取和分析，不需要我手动触发  
**So that** 我每天打开就能看到最新内容，不同频率的报告自动出现

**四种触发模式（互不干扰）：**

| 模式 | 触发方式 | 做什么 | 结果去哪 |
|------|---------|--------|---------|
| **新增股票** | 用户手动添加 | 立即对这一只跑完整 pipeline | 持仓卡显示分析结果 |
| **日报** | 每天 08:00 CST | 所有持仓各自爬取 + 各自分析 | 更新各股详情页 + Discord 推送 |
| **周报** | 每周一 08:00 CST | 过去7天新闻聚合 + 组合周总结 | 新增 weekly 报告 + 推送 |
| **月报/季报** | 每月1日 / 每季首日 | 深度分析 + 组合回顾 | 新增 monthly/quarterly 报告 |
| **宏观快照** | 每天 07:30 CST | CNY/USD、指数、商品、F&G | Pulse Bar 数据更新 |

**Acceptance Criteria:**
- 每种模式独立的 launchd plist，互不影响
- 任务完成后推送 Discord 通知（日报简短，周/月报详细）
- 用户手动「巴菲特看此刻」按钮 = **只触发宏观快照**（快，<15秒，不重跑 LLM）
- 全量 LLM 重分析只在：① 定时任务 ② 手动添加新股票 ③ 用户主动点「重新分析」时触发
- 同一只股票当天已分析过，定时任务不重复跑（除非强制）

---

### US-09 · 模块化市场信息流（被动内容）

**As a** 用户  
**I want to** 看到与我持仓无关的市场全景信息  
**So that** 即使没有持仓，也能持续学习市场动态

**本地模块（NZ）：**
- NZ Herald / Interest.co.nz 商业新闻
- RBNZ 利率决议 / OCR 声明
- NZX 重要公告
- NZX 行业板块动态

**国际模块：**
- A股三大指数（上证 / 深证 / 创业板）
- 美联储 FOMC 声明
- 商品价格（铜 / 铁矿石）
- CNN Fear & Greed Index 解读
- CNY/USD 汇率趋势

**展示方式：** NYT 双栏排版，每条带「分类标签」（RBNZ / FOMC / 宏观 / 市场）

---

### US-10 · 巴菲特++分析模型

**As a** 系统  
**I want to** 用扩展的分析框架处理所有股票  
**So that** 分析结论比纯巴菲特三问更有深度

**分析维度：**

| 维度 | 来源 |
|------|------|
| 护城河 | 巴菲特：品牌/网络效应/成本优势/转换成本 |
| 管理层质量 | 巴菲特：资本配置历史、股东信 |
| 安全边际 | 巴菲特：内在价值 vs 市价 |
| Too Big To Fail | 系统重要性：政府救助概率、监管保护 |
| 行为经济学信号 | Kahneman：市场过度反应、锚定效应、羊群效应 |
| 资金流向信号 | 主力净流入/流出趋势（A股专项） |
| 宏观敏感度 | 利率敏感度、汇率敏感度、大宗商品相关性 |

**输出格式（结构化）：**
```
护城河：[宽/窄/无] — [一句解释]
管理层：[优/中/差] — [一句解释]
估值：[低估/合理/高估] — PE/PB vs 历史均值
资金：[流入/流出] [金额]
行为信号：[过度恐惧/正常/过度贪婪]
TBTF：[是/否/部分]
─────────────────────────
结论：[买入/持有/减持/卖出]
原因：[两句话，直接]
```

---

### US-11 · ML 模型（学习项目）

**As a** 开发者（用户）  
**I want to** 用机器学习方法训练一个辅助判断模型  
**So that** 在练习 ML 的同时让分析更准确

**阶段规划：**

| 阶段 | 目标 | 技术 |
|------|------|------|
| Phase 1 | 数据积累 | 每次分析结果存 DB，包含特征向量 |
| Phase 2 | 情感分析 | 对新闻标题做 NLP 情感打分（positive/negative/neutral）|
| Phase 3 | 特征工程 | 价格动量 + 资金流 + 情感分 + 宏观指标 → 特征矩阵 |
| Phase 4 | 分类模型 | 预测「下周涨/跌/平」，用 scikit-learn 训练 |
| Phase 5 | 回测 | 用历史数据验证模型准确率 |

**DB 需要提前设计好的字段：** 见 Section 三

---

## 三、数据库设计（重构）

> 当前 DB 混入了硬编码数据，需要清洁重建。

### 核心原则
1. **用户数据**（watchlist、分析结果）与**系统数据**（市场新闻、宏观数据）完全分离
2. **无硬编码股票**，所有股票从用户添加开始
3. 每只股票独立存储分析结果，支持历史对比
4. 预留 ML 特征字段

### 表结构

```sql
-- 用户
users (id, email, display_name, locale, region, created_at)

-- 用户自选股（关联关系，不含分析）
user_watchlist (user_id, stock_code, added_at, notes)

-- 股票基础信息（全局，不属于某个用户）
stocks (
  code TEXT PRIMARY KEY,   -- e.g. "NVDA", "600900.SS", "FPH.NZ"
  name TEXT,
  market TEXT,             -- us/cn/hk/nz
  exchange TEXT,           -- NYSE, SSE, HKEX, NZX
  sector TEXT,
  currency TEXT,
  last_updated TIMESTAMP
)

-- 股票价格快照（每次爬取存一条）
stock_prices (
  id INTEGER PRIMARY KEY,
  code TEXT,
  price REAL,
  change_pct REAL,
  volume REAL,
  market_cap REAL,
  pe_ratio REAL,
  fetched_at TIMESTAMP
)

-- 新闻（按股票）
stock_news (
  id TEXT PRIMARY KEY,     -- MD5(title+link)
  code TEXT,
  title TEXT,
  link TEXT,
  source TEXT,
  sentiment REAL,          -- ML Phase 2: -1.0 to 1.0
  publish_time TEXT,
  fetched_date TEXT
)

-- 分析结果（每股每期一条）
analysis_results (
  id INTEGER PRIMARY KEY,
  code TEXT,
  period TEXT,             -- daily/weekly/monthly/quarterly
  analysis_date TEXT,
  moat TEXT,               -- 护城河
  management TEXT,         -- 管理层
  valuation TEXT,          -- 估值
  fund_flow TEXT,          -- 资金
  behavioral TEXT,         -- 行为信号
  tbtf TEXT,               -- Too Big To Fail
  conclusion TEXT,         -- 结论
  reasoning TEXT,          -- 原因
  grade TEXT,              -- A/B+/B/B-/C/D
  raw_output TEXT,         -- 完整 LLM 输出
  -- ML 特征字段（Phase 1 开始积累）
  feat_price_momentum REAL,
  feat_sentiment_avg REAL,
  feat_fund_flow_net REAL,
  feat_pe_vs_hist REAL,
  feat_macro_fear_greed INTEGER
)

-- 系统宏观数据（与用户无关）
market_data (
  id INTEGER PRIMARY KEY,
  data_type TEXT,          -- nzx50/fear_greed/cny_usd/cn_indices/commodities
  payload TEXT,            -- JSON
  fetched_at TIMESTAMP
)

-- 系统新闻（NZ Herald/RBNZ/FOMC 等，与用户无关）
market_news (
  id TEXT PRIMARY KEY,
  region TEXT,             -- nz/global
  category TEXT,           -- market/rbnz/fomc/macro
  title TEXT,
  link TEXT,
  source TEXT,
  publish_time TEXT,
  fetched_date TEXT
)

-- Pipeline 任务状态（异步追踪）
pipeline_jobs (
  id INTEGER PRIMARY KEY,
  code TEXT,
  job_type TEXT,           -- add_stock/daily/weekly/monthly/quarterly
  status TEXT,             -- pending/running/done/failed
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error TEXT
)
```

---

## 四、技术架构

```
前端 (Flask + Jinja2)
  ├── 首页 (index)                ← US-04 / US-05
  │   └── 多选模式 checkbox UI    ← US-12
  ├── 单股详情页 (stock/<code>)   ← US-06
  ├── 组合分析页 (portfolio)      ← US-07
  │   ├── 全部持仓: /portfolio
  │   └── 选中子集: /portfolio?codes=NVDA,600031
  └── 设置 (settings)

后台任务（四种独立模式）
  ├── pipeline.py run_pipeline()  ← 单股 pipeline，US-03 / US-08 都调它
  ├── launchd: pipeline.py daily  ← 每天 08:00 CST，所有持仓
  ├── launchd: periodic_digest.py weekly/monthly/quarterly
  └── launchd: macro_fetch.py     ← 每天 07:30 CST，宏观快照

API 层
  ├── POST /add                   ← 添加股票 + 触发单股 pipeline
  ├── POST /api/analyze/<code>    ← 手动触发单股重新分析
  ├── POST /api/analyze-batch     ← 批量触发选中股票（US-12 A）
  ├── GET  /api/search?q=         ← 模糊搜索（AKShare + yfinance）
  ├── GET  /api/job/<id>          ← 查询 pipeline 状态（前端轮询）
  ├── GET  /api/letter/<code>     ← 读巴菲特信 HTML
  ├── POST /api/portfolio-analyze ← 触发组合级 LLM 分析（US-07 B）
  └── POST /fetch                 ← 只更新宏观快照（不跑 LLM）

数据库 (SQLite → 可迁移 PostgreSQL)
  ├── 用户表: users, user_oauth, user_watchlist
  ├── 股票表: stocks, stock_prices, stock_news, stock_fund_flow
  ├── 分析表: analysis_results（单股）, portfolio_analysis（组合）← 待加
  ├── 报告表: reports（周/月/季 digest）
  ├── 系统表: market_data, market_news
  └── 任务表: pipeline_jobs
```

### 新增 DB 表：portfolio_analysis
```sql
CREATE TABLE portfolio_analysis (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  codes        TEXT,     -- JSON 数组，e.g. '["NVDA","600031"]'
  analysis_date TEXT,
  letter_html  TEXT,     -- 组合分析信（LLM 生成）
  conclusion   TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);
```

---

## 五、已确认决策

| 问题 | 决定 |
|------|------|
| ML 第一版？ | **否**。Phase 1 字段写进 DB schema 备用，ML 是后续学习项目 |
| 模糊搜索数据源 | **AKShare（A股）+ yfinance（美港NZ）双引擎**，结果合并去重。A股列表 app 启动时后台预热（~10秒），首次搜索前可能结果为空 |
| 推送渠道 | Discord（你）+ Bear · 妈妈推送 → 第二版 PWA Web Push |
| 单用户 vs 多用户 | **轻量多用户**：admin（你）+ subscriber（妈妈，只收推送，你帮她管理自选股）|
| 侧边栏 | **可收起**（桌面默认展开，移动端默认收起）|
| 单股 vs 组合 | **三种视图**：① `/stock/<code>` 单股深度 ② `/portfolio` 全部持仓横向对比 + 组合分析信 ③ `/portfolio?codes=A,B` 选中 N 只的子组合视图 |
| 分析触发逻辑 | 新增股票→立即触发；定时任务→全量；手动「重新分析」→单只；批量选→选中的；「巴菲特看此刻」→**只更新宏观，不重跑 LLM** |
| 数据库 | SQLite 足够（个人使用量级），结构兼容未来迁移 PostgreSQL |
| 组合分析 LLM | **手动触发**，不自动跑，避免无谓消耗 Groq API |

---

## 六、用户 Profile 设计

### 你的账号（管理员）
- 全功能：添加/删除股票、查看分析、管理妈妈的 profile
- 推送：Discord + Bear

### 妈妈的账号（简化）
- 在系统里有独立的 `user_id`，自选股独立
- **不需要登录 app**，只接收推送
- 推送：企业微信 Webhook（你建一个群，她进群）
- 你在自己的后台界面帮她管理自选股（在设置页里有「管理其他用户」入口）

### 企业微信 Webhook 集成
```python
# 10 行代码，和 Discord 完全一样
import requests

def send_wecom(webhook_url: str, content: str):
    requests.post(webhook_url, json={
        "msgtype": "markdown",
        "markdown": {"content": content}
    })
```
申请流程：企业微信后台 → 群机器人 → 复制 Webhook URL → 存到 `.env`

---

## 七、ML 数据积累设计（Phase 1，第一版即写入）

ML 模型虽然后做，但**第一版就要开始积累训练数据**，不然等你想做 ML 时没有历史数据。

每次 `analysis_results` 写入时，同时计算并存储：

```sql
feat_price_momentum REAL,   -- 过去5日涨跌幅均值
feat_sentiment_avg  REAL,   -- 过去7日新闻情感均值（暂时留 NULL，Phase 2 填）
feat_fund_flow_net  REAL,   -- 主力净流入（A股）/ NULL（其他）
feat_pe_vs_hist     REAL,   -- 当前PE / 过去1年均值PE
feat_fear_greed     INTEGER -- 当日 Fear&Greed 指数
```

**ML 训练集查询示例：**
```sql
-- 未来可以这样拉特征+标签
SELECT
  a.feat_price_momentum, a.feat_sentiment_avg, a.feat_fund_flow_net,
  a.feat_pe_vs_hist, a.feat_fear_greed,
  -- 标签：7天后涨跌
  (p2.price - p1.price) / p1.price AS label_7d_return
FROM analysis_results a
JOIN stock_prices p1 ON p1.code = a.code AND p1.fetched_at = a.analysis_date
JOIN stock_prices p2 ON p2.code = a.code AND p2.fetched_at = a.analysis_date + 7
```

---

## 八、模糊搜索实现方案

### 搜索流程
```
用户输入 "nvidia" / "英伟达" / "600900"
         ↓
[并行搜索]
AKShare: ak.stock_info_a_code_name() → A股名称/代码匹配
yfinance: yf.Search("nvidia") → 美股/港股/NZX
         ↓
[合并去重，按相关性排序]
         ↓
返回候选列表（最多10条）:
  [NVDA]  NVIDIA Corp       · NYSE · $875.39
  [600900.SS] 长江电力      · SSE  · ¥25.41
  [FPH.NZ]  Fisher & Paykel · NZX  · $26.80
```

### AKShare vs yfinance 详细对比
| | AKShare | yfinance |
|---|---|---|
| A股中文名搜索 | ✅ 原生支持「英伟达」→ 返回 A 股相关概念股 | ❌ |
| A股代码搜索 | ✅ 「600900」直接返回长江电力 | ⚠️ 需要加 `.SS` 后缀 |
| 美股搜索 | ❌ 有限 | ✅ 「nvidia」→ NVDA，准确 |
| 港股搜索 | ⚠️ 有限 | ✅ 「00700.HK」 |
| NZX 搜索 | ❌ | ✅「FPH.NZ」|
| NZ IP 速度 | 慢（国内接口）| 中等 |

---

---

### US-14 · 渐进式信息层级（Progressive Disclosure）

**As a** 用户
**I want to** 首页只看到最关键的内容，更深的功能按需进入
**So that** 我每次打开不会被一堆按钮和选项压倒

**设计原则：由简入深**
```
第一层（首页）：今天发生了什么？
  → 持仓简报（最新评级 + 价格）
  → 市场信息流（新闻）
  → 只有一个主操作：「巴菲特看此刻」（更新宏观数据）

第二层（专项页面）：我要管理/深入研究
  → 我的选股（/watchlist）：管理、多选、批量操作
  → 单股详情（/stock/<code>）：深度分析
  → 组合分析（/portfolio）：横向对比

第三层（报告归档）：我要回顾历史
  → 报告中心（/report）：所有日报/周报/月报/季报
```

**首页只保留：**
- 持仓简报卡片（名称/价格/一句话结论）
- 「管理 →」入口（去 /watchlist）
- 「+ 添加」按钮
- 市场信息流（两栏新闻）
- 「巴菲特看此刻」（唯一的主操作按钮）
- 若有最新报告：一行小字「今日简报已更新 · 查看 →」，不是按钮

**首页移除的内容：**
- Weekly / Monthly / Quarterly 报告按钮 → 移到 /report 页
- 「+ Generate Digest」按钮 → 移到 /report 页
- 所有历史报告链接 → 移到 /report 页

**报告生成逻辑（自动化）：**
- 日报：launchd 每天 08:00 CST 自动生成，无需用户触发
- 周报：每周一自动生成
- 月报/季报：固定日期自动生成
- 用户在 /report 页可手动触发「重新生成」（admin only）

**Acceptance Criteria:**
- 首页 masthead 只有一个主操作按钮
- 所有报告相关操作统一在 /report 页
- 报告自动生成后首页出现一行低调提示，不打断阅读

---

### US-15 · 新闻情境化（参考 Yahoo Finance）

**As a** 用户
**I want to** 在首页信息流的新闻旁看到「这条新闻影响我持有的哪只股票」
**So that** 我不需要自己判断每条新闻和我持仓的关联

**设计：**
```
[FOMC] 美联储维持利率不变
彭博社 · 今天
影响你的持仓：NVDA ↑  三一重工 ↓（基于 AI 判断）
```

**实现逻辑：**
- 爬取新闻时，跑一次轻量 LLM 判断：「这条新闻对用户持有的 [代码列表] 各自是利好/利空/中性？」
- 结果存入 `stock_news.sentiment` 字段（已有）
- 首页信息流渲染时，若该新闻与用户自选股相关，加一行小字

**Acceptance Criteria:**
- 信息流新闻卡片下方可选渲染影响标签
- 无自选股时不显示此行
- LLM 判断失败时静默降级（不显示标签，不报错）

---

### US-16 · Watchlist 缩略图模式（参考 StockCharts CandleGlance）

**As a** 用户
**I want to** 在「我的选股」页面一屏快速扫视所有持仓的评级和走势
**So that** 持仓多时不需要上下滚动才能总览

**视图切换：**
```
[卡片模式]  [缩略图模式]   ← 右上角两个图标切换
```

**缩略图模式每格显示：**
```
NVDA · A                 三一重工 · B+
$875  +2.1%             ¥15.2  -0.3%
[====迷你走势线====]     [====迷你走势线====]
```
- 每行 3-4 格，一屏可看 12-16 只
- 点击进入单股详情页
- 不显示巴菲特信、推理文字等深层内容

**Acceptance Criteria:**
- 视图偏好存在 localStorage，刷新后保持
- 缩略图模式不显示操作按钮（移除/分析）

---

### US-17 · 巴菲特++评分雷达图

**As a** 用户
**I want to** 在单股详情页侧边栏看到一个 5 维评分的迷你雷达图
**So that** 我能直觉地理解这只股票的优劣势分布，不用逐行读文字

**5 个维度（对应 analysis_results 字段）：**
- 护城河（moat）
- 管理层（management）
- 估值（valuation）
- 资金流向（fund_flow_summary）
- 宏观敏感度（macro_sensitivity）

**评分映射：**
- 「宽/优/低估/流入/低敏」→ 5 分
- 「中/中/合理/中性/中敏」→ 3 分
- 「窄/差/高估/流出/高敏」→ 1 分
- LLM 文字用正则或小模型提取分值

**实现：** 用 SVG 或 Canvas 画五边形雷达图，不引入 Chart.js 等大库

**Acceptance Criteria:**
- 侧边栏巴菲特评级卡下方显示雷达图
- 没有分析数据时不显示（不显示空雷达图）
- hover 每个顶点显示原始文字说明

---

---

### US-18 · 首页题头重设计（有持仓时）

**As a** 有持仓的用户
**I want to** 进入首页看到简洁有仪式感的题头，而不是一堆数据条
**So that** 每天打开有种"翻开巴菲特信"的感觉，而不是看仪表盘

**布局：**
```
私人巴菲特          2026年4月6日 · 星期日
─────────────────────────────────────────────
         [ 巴菲特看此刻 ]      ← 大按钮，居中或左对齐
         今日简报已更新 · 查看 →  ← 微提示，仅有报告时显示
─────────────────────────────────────────────
[我的持仓]
  卡片...
```

**Acceptance Criteria:**
- 去掉 Pulse Bar（NZX50 / Fear&Greed 那行），有持仓时不显示
- 「巴菲特看此刻」按钮放大，作为页面视觉重心
- 日期显示在 masthead 右侧或副标题位置
- Pulse Bar 数据不删除，只是不在首页展示（保留 API，将来可在详情页用）

---

### US-19 · 持仓与新闻视觉分层

**As a** 用户
**I want to** 持仓区和新闻区有明显不同的视觉权重
**So that** 眼睛自然先落在持仓，新闻退到背景层，想看就往下滚

**视觉方案：**
```
[持仓区]  纸白底 (#faf9f7)，卡片有细边框，字体深色 — 主层
────────────────────────────────── 分隔线
[新闻区]  浅灰底 (#f0eeea)，字体降色 (#666)，padding 缩小 — 次层
```

**Acceptance Criteria:**
- 两区块有明显灰度差，不需要任何文字标注用户也能感知层级
- 新闻区标题字号比持仓区小 1-2px
- 分隔线或色块边界清晰

---

### US-20 · 导航栏精简

**As a** 用户
**I want to** 导航栏只看到最核心的入口
**So that** 界面不被次要功能占据注意力

**精简后导航：**
```
私人巴菲特    我的选股    [中文/EN]    [头像]
                                          ↓ 下拉菜单
                                        设置
                                        退出
```

**Acceptance Criteria:**
- 删除「仪表盘」链接（首页通过 logo/品牌名点击进入）
- 删除「报告」独立链接（报告在头像下拉或通过首页提示进入）
- 退出、设置移入头像下拉菜单
- 无头像时显示首字母圆形占位

---

### US-21 · NZ 本地新闻修复（Bug）

**As a** 用户
**I want to** 首页本地栏显示新西兰新闻
**So that** 我能看到 NZ 市场动态

**已知问题：** 本地新闻区显示空白，`fetch_nz_news` / `fetch_nz_market_news` 未正常返回数据

**Acceptance Criteria:**
- 排查并修复 NZ 新闻源（NZ Herald RSS / Interest.co.nz）
- 若数据源不可用，显示"暂无 NZ 新闻，点刷新重试"而不是空白

---

### US-22 · 股票详情页导航优化

**As a** 用户
**I want to** 在股票详情页有清晰的导航
**So that** 我能方便地回到选股列表

**变更：**
- 返回按钮：去掉"首页"文字，只保留 ← 图标（或只显示品牌名）
- 新增「← 全部选股」按钮，跳转 `/watchlist`
- 布局：`← 品牌名`（回首页） · `← 全部选股`（回 /watchlist）

**Acceptance Criteria:**
- 两个导航入口清晰区分，不造成混乱
- 移动端也能正常显示

---

### US-23 · 公司价值档案页

**As a** 用户
**I want to** 点击股票名称进入一个专门展示该公司基本面数据的页面
**So that** 我能看到巴菲特评级背后的原始数据依据

**触发方式：** 单股详情页（/stock/<code>）顶部的公司名称可点击

**页面内容（/stock/<code>/fundamentals）：**
```
三一重工 · 基本面档案
────────────────────────────────────
[盈利能力]          [财务健康]
ROE: 18.2%          资产负债率: 42%
净利润率: 12.1%      流动比率: 1.8
收入增长(3Y): +15%   自由现金流: 正向

[护城河评估]
品牌    ██████░░░░  60%
专利    ████░░░░░░  40%
规模    ████████░░  80%
转换成本 ██████░░░░  60%

[评级历史时间线]
2026-04  B+ · 持有观察
2026-03  B  · 合理估值
2026-02  C+ · 等待机会

[主力资金历史]
近30日累计流入: +2.3亿
```

**Acceptance Criteria:**
- URL: `/stock/<code>/fundamentals`
- 数据来自 DB（analysis_results / stock_prices / stock_fund_flow）
- 若数据不足，显示"数据积累中"占位
- 有历史评级时间线（至少显示最近 5 次）

---

### US-28 · 我的选股页重设计（侧边栏 + 快捷操作）

**参考：** COMPETITOR_UX.md → TradingView（分组+快速操作）+ Seeking Alpha（评分列）+ StockCharts（缩略图模式）

**As a** 用户  
**I want to** 在「我的选股」页面有一个左侧边栏做筛选/排序，主区域专心展示股票  
**So that** 我能快速定位需要关注的股票，不用滚动找

**布局：**
```
[左侧边栏 220px]          [主内容区]
─────────────────         ──────────────────────────────
我的选股（6）              [  卡片模式  ][  缩略图模式  ]  + 添加
─────────────────         ──────────────────────────────
排序                       [三一重工卡片]  [阳光电源卡片]
  ○ 评级（高→低）          [复星医药卡片]  [中金公司卡片]
  ○ 涨跌幅
  ○ 最近分析时间           缩略图模式（US-16 逻辑）：
  ○ 资金流向               ┌──────┐ ┌──────┐ ┌──────┐
─────────────────         │ 三一  │ │ 阳光  │ │ 复星  │
筛选                       │  B+  │ │  A   │ │  C   │
  □ 只看分析>7天的          │+1.2% │ │+3.1% │ │-0.5% │
  □ 评级B以上               └──────┘ └──────┘ └──────┘
  □ 主力资金流入
─────────────────
批量操作
  [全选]  [反选]
  [批量分析]
  [导出]
─────────────────
[+ 添加新股票]
```

**卡片快捷操作（Quick Actions，不离开列表）：**
- 每张卡片 hover 时右侧出现图标：[分析] [详情 →] [删除]
- 不再需要进入详情页才能触发分析

**卡片模式信息密度（参考 Seeking Alpha）：**
```
三一重工 600031          B+  持有    ¥21.5  +1.2%
工程机械 · A股           护城河收窄·ROIC 12.6%·FCF良好
[主力净流出 0.3亿]       最近分析：今天
```

**Acceptance Criteria:**
- 侧边栏排序/筛选状态存入 localStorage，刷新保持
- 缩略图模式复用 US-16 设计
- 移动端侧边栏折叠为顶部筛选条
- 快捷 [分析] 按钮复用现有 triggerAnalysis() 逻辑
- 现有底部批量操作栏迁移到侧边栏「批量操作」区

---

### US-24 · 预测追踪与模型复盘

**As a** 系统开发者（周宇）  
**I want to** 追踪每次"买入/持有/减持/卖出"预测的实际结果  
**So that** 我能知道模型哪里准、哪里不准，持续改进

**本质：** 这是一个预测系统。每次分析 = 一次预测。预测需要被验证。

**数据流：**
- 分析完成时：记录 `analysis_date` + `grade` + `conclusion` + 当时价格（已有）
- 7天后、30天后：launchd 定时任务回填 `label_7d_return` / `label_30d_return`（字段已在 DB 中）
- 判定规则：买入预测 + 实际涨 >3% = 正确；买入 + 实际跌 >3% = 错误；±3% 内 = 中性

**UI（/report/accuracy 或嵌入 /report 页）：**
```
预测准确率追踪
──────────────────────────────────────────
买入预测（共23次）   7日准确率 61%   30日准确率 57%
持有预测（共41次）   7日准确率 72%   30日准确率 68%
减持预测（共8次）    7日准确率 50%   30日准确率 63%

表现最好的信号：FCF质量>1.5x（准确率79%）
表现最差的信号：新闻利好（准确率44%，接近随机）

最近错误的预测：
  三一重工 2026-03-12  买入 → 实际 -8.2%  可能原因：忽略了融资余额大幅流出
  阳光电源 2026-03-08  持有 → 实际 +15%   可能原因：低估了护城河拓宽信号
```

**Acceptance Criteria:**
- launchd 每天运行一个 `backfill_returns.py` 脚本，回填7/30日实际收益
- `/report/accuracy` 页面展示按预测类型的准确率
- 表格可按时间、股票、信号类型筛选
- 错误案例高亮，附"可能原因"字段（可手动填写）

---

### US-25 · 源代码保护与项目提交包

**As a** 学生（周宇）  
**I want to** 把项目提交给老师评审时，保护 API key 和敏感配置  
**So that** 老师能跑起来看效果，但我的密钥不会泄露

**Acceptance Criteria:**
- `.env.example` 列出所有需要的环境变量，有注释说明如何获取
- `config.py` 从环境变量读取 API key，不硬编码
- `README.md`（英文）：项目背景、如何本地运行、技术栈说明
- 提交前 checklist：确认 `.env` 在 `.gitignore`、DB 文件不上传、无硬编码密钥
- 可选：提供一个 `demo_mode` 开关，用 mock 数据代替实时 API 调用，方便评审

---

### US-26 · 个人贡献展示页（给老师看的 About 页）

**As a** 学生（周宇）  
**I want to** 有一个页面展示这个项目是什么、我做了什么  
**So that** 老师能快速理解项目背景和我的贡献

**页面内容（/about）：**
```
Personal Buffett — An AI-powered value investing assistant

Project Background
  Built for my mum — a retail A-share investor in China who struggles
  to filter signal from noise. She needed something that speaks Buffett,
  not Bloomberg.

What I Built
  · Real-time A-share / NZX / US stock data pipeline
  · Buffett analysis framework (GREAT/GOOD/GRUESOME classification)
  · Wall Street-grade signals: ROIC, Owner Earnings, pledge ratio,
    margin balance, institutional holdings
  · Automated daily report via launchd + Discord push

Tech Stack
  Flask · SQLite · AKShare · yfinance · Groq (Llama 3) · Chart.js

My Contribution
  [开发时间轴 / 功能列表 / 技术决策说明]
```

**Acceptance Criteria:**
- 页面对未登录用户可见
- 纯静态 HTML，不依赖 DB
- 英文，专业但不失个人风格

---

### US-27 · 教师版 Demo（NZX 优先，英文界面）

**优先级：** 低（妈妈版完成后再做）

**As a** 老师（NZ 本地白人，不炒 A 股）  
**I want to** 看到一个专注于 NZX 和美股的英文版本  
**So that** 我能真实体验产品价值，而不是看着中文 A 股数据困惑

**与现有版本的差异：**
- 默认语言：英文
- 默认市场：NZ / US
- 首页示例股票：ATM.NZ、SPK.NZ、Apple、Nvidia
- 隐藏 A 股专属功能（主力资金、融资余额、质押比例）
- 巴菲特信用英文生成（切换 Groq prompt 语言）
- 数据来源脚注：NZX data via yfinance · News via Google News RSS

**Acceptance Criteria:**
- 不是新系统，是现有系统的 locale=en + region=nz 模式的完整体验
- 所有界面文字完整英文化（无遗漏的中文）
- A 股专属 UI 模块在 region=nz 时自动隐藏

---

### US-29 · Pipeline 超时保护

**As a** 用户  
**I want to** 点击「巴菲特分析」后在 60 秒内看到结果（或失败提示）  
**So that** 不会因为某个 AKShare API 卡住而等五分钟

**根本原因：** AKShare 没有内置超时，从 NZ 访问国内服务器每步 10-30s，6步串行 = 5分钟

**解决方案：**
- 每个 pipeline 步骤用 `concurrent.futures.ThreadPoolExecutor(timeout=30s)` 包裹
- 超时则跳过该步骤（打 log），不阻塞后续步骤
- ST股（代码含 "ST"）跳过 3.6 (advanced) 和 3.8 (signals)——数据质量差，意义不大
- 总 pipeline 软上限：120 秒（超过则强制结束并标 `done`）

**Acceptance Criteria:**
- 分析结果在 ≤ 90 秒内出现（正常情况 30-60 秒）
- 某步超时时，前端日志能看到 "⏱ [步骤] 超时，跳过" 提示
- ST股分析不再卡在 3.6/3.8

---

### US-30 · 我的选股侧边栏重设计（目录式）

**As a** 用户  
**I want to** 侧边栏是一个「文档柜目录」——显示股票名称和关键状态，操作控件收起来  
**So that** 减少认知负载，侧边栏的主角是「我的持仓列表」，不是排序筛选表单

**新设计：**
```
侧边栏
├── [排序图标] [筛选图标]  ← 点击展开浮层，不常驻
└── 股票目录（每条一行）
    ├── 评级徽章 (A/B+…)
    ├── 股票名称
    ├── 结论标签 (买入/持有…)
    └── 点击 → 主区域滚动到该卡片并高亮
    
底部
└── + 添加股票 按钮
```

**交互规则：**
- 排序/筛选：图标按钮 → 点击展开小浮层（popover），选完自动收起
- 目录条目高亮：点击侧边栏条目 → 主区对应卡片高亮（outline 闪一下），页面滚动到它
- 批量操作：主区卡片左侧勾选框，勾选后底部出现批量操作栏（不在侧边栏）
- 添加股票：只保留侧边栏底部「+ 添加」按钮，点击主区展开添加表单

**Acceptance Criteria:**
- 侧边栏宽度 ≤ 180px，无任何常驻表单控件
- 排序/筛选浮层点击外部自动关闭
- 点击目录条目主区滚动 + 高亮动画（0.3s）
- 批量操作栏仅在有勾选时出现（fixed bottom bar）
- 移动端侧边栏变顶部水平滚动目录

---

### US-31 · 我的选股：搜索 + 视图 + 选择模式（重定义）

**As a** 用户  
**I want to** 选股页默认干净无打扰——点哪里都能进详情，需要批量操作时才进「选择模式」  
**So that** 日常浏览不被复选框干扰，要批量分析时也流程清晰

---

**工具栏布局（从左到右）：**
```
我的选股 N    [搜索框]    [排序▾]  [卡片↔列表]  [分析]  [+ 添加]
```

- **排序▾**：点击展开 popover，选项：默认 / 评级高→低 / 涨跌幅 / 最近分析，选后立即排序并关闭
- **卡片↔列表**：单个切换按钮，当前是卡片时按钮显示「列表」，当前是列表时显示「卡片」，localStorage 持久化
- **分析**：点击进入「选择模式」
- **筛选按钮**：删除（功能未定，先不做）

---

**默认模式（无复选框）：**
- 卡片整体可点击 → 进入详情页（不只是股票名）
- 列表行整体可点击 → 进入详情页
- 操作区（读信 / 移除）仍可独立点击，阻止冒泡

---

**选择模式（点「分析」进入）：**
- 所有卡片/行左侧出现复选框
- 点击卡片 = 切换复选框（不跳转）
- 工具栏「分析」变成「取消选择」
- 底部 batch-bar 出现：`已选 N 只  [重新分析]  [组合分析]  [取消]`
- 点「取消」或取消所有勾选 → 退出选择模式

---

**搜索：**
- 搜索框实时过滤（名称 / 代码），卡片和列表视图同步响应
- 清除按钮（×）

---

**列表模式（视图切换后）：**
```
评级  名称        市场  价格     涨跌    结论   日期    操作
A     阳光电源    CN    ¥68.10  +1.2%   买入   04-05  ↻ 读信 移除
B+    三一重工    CN    ¥24.30  -0.4%   持有   04-05  ↻ 读信 移除
```
- 无复选框列（默认模式）；进入选择模式后列表行首出现复选框
- 移动端自动降级为卡片

---

**Acceptance Criteria:**
- 默认不显示复选框
- 整个卡片区域（非操作按钮）可点击跳转详情页
- 视图切换按钮一键生效，localStorage 持久化
- 排序 popover 选后立即生效
- 点「分析」进入选择模式，复选框出现，batch-bar 出现
- 点「取消」退出选择模式，复选框消失

---

### US-32 · 股票详情页重设计（删侧边栏，头部融合）

**As a** 用户
**I want to** 详情页不要侧边栏——评级/关键数据直接在头部，Tab 全宽展示
**So that** 手机/窄屏也能正常浏览，没有冗余重复信息

**新布局：**
```
← 全部选股

三一重工                             ¥24.30  +1.2%
CN · 600031 · 工程机械               B+ 持有

PE 12.3x · 市值1980亿 · 主力+0.5亿

━━━━━━━━━━━━━━━━━━━━━━━━━━━
[今日简报]  [新闻 6]  [历史分析 3]  [数据]  [价值档案 →]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
... tab content（全宽）...
```

**Acceptance Criteria:**
- 删除 `.stock-sidebar` 及所有 sidebar 相关 CSS 和 JS
- 头部新增 stats bar：PE / 市值 / 主力资金（A股才显示）
- 评级 + 结论 徽章放在头部右侧或价格下方
- Tab 内容区宽度 = 页面全宽（max 900px）
- 移动端头部两栏变单栏竖排

---

---

### US-33 · 我的选股三分区：持有 / 观察 / 卖出

**As a** 用户  
**I want to** 把自选股按"持有中 / 在观察 / 已卖出"分开管理  
**So that** 我能一眼看清楚自己的真实持仓和待决策池，不把已卖的和在看的混在一起

---

**三个分区（DB `status` 字段）：**

| 状态 | 含义 | 入口 |
|---|---|---|
| `watching` | 在观察，尚未买入（默认） | 添加股票时默认 |
| `holding` | 持有中 | 移动卡片 / 操作菜单 |
| `sold` | 已卖出 | 移动卡片 / 操作菜单 |

**移动交互：**
- 每张卡片有「移至…」操作按钮，弹出状态选择 + 日期选择器
- 日期默认 = 今天，可修改（补录过去操作）
- 移到「持有」→ 记录 `buy_date`，可选填 `buy_price`（不填则系统从历史行情拉当天收盘价）
- 移到「卖出」→ 记录 `sell_date`，可选填 `sell_price`

**页面布局：**
```
我的持有 (N)          我的观察 (N)          我的卖出 (N)
─────────────────  ─────────────────  ─────────────────
[卡片 卡片 卡片]    [卡片 卡片]          [卡片 卡片]
```
- 三列横排（桌面）；手机竖排 Tab 切换
- 工具栏：搜索/排序/视图/分析 按钮对三个区域均生效
- 「卖出」区卡片样式灰显（表示历史记录），不再触发自动分析

**DB 变更：**
- `watchlist_stocks` 表新增字段：`status TEXT DEFAULT 'watching'`、`buy_date DATE`、`buy_price REAL`、`sell_date DATE`、`sell_price REAL`
- 自动 ALTER TABLE 兼容旧 DB（`_migrate()` 模式）

**Acceptance Criteria:**
- 添加股票时状态默认为 `watching`
- 三个分区各自显示对应状态的股票
- 移动卡片后状态立即更新，日期记录准确
- 旧数据（无 status 字段）自动迁移为 `watching`

---

### US-34 · 行为金融分析增强（Kahneman × A股情绪）

**As a** 用户  
**I want to** 分析报告里除了巴菲特的基本面框架，还有一个「行为金融」模块，直接点名常见的心理陷阱  
**So that** 我或我的家人看到的不只是"估值合理"，而是"你现在拿着这只股票是因为价值，还是因为舍不得卖？"

---

**灵感来源（已读，纳入 prompt）：**
- *Thinking, Fast and Slow*（Kahneman）：损失厌恶、锚定效应、前景理论
- *Freakonomics*（Levitt）：真实激励 vs 表面激励；信息不对称

---

**「行为金融」字段增强——LLM 必须覆盖以下三个子维度：**

**① 理性人检验（Sunk Cost Debiasing）**
> "忘记你的买入成本。如果今天你手里是等值现金，你愿意以现在这个价格买入吗？"

如果分析结论是 GRUESOME / 卖出，必须明确写出：
> "持有这只股票的唯一理由如果是'已经亏了不甘心'，那这是情绪，不是理由。"

**② A股特有情绪信号**
- ST/风险警示股 → 触发「退市风险」警告 + 行为提示（彩票心理：期待反弹的人多，但大多数 ST 最终退市）
- 主力净流出 + 散户情绪高涨 → 「博傻信号」——最后一个拿包的人
- 近期连续涨停 → 追涨 FOMO 警告
- 近期连续跌停 → 恐慌卖出 vs 价值机会判断

**③ 锚定效应识别**
- 如果用户有买入价且当前价格低于买入价 20%+：提示锚定效应
- 建议用语：不是"你亏了X%"，而是"今天的价格是否仍然高于内在价值？这才是该问的问题"

---

**Prompt 增强方向（`_run_analysis` 的 system_msg 新增段落）：**

```
【行为金融分析指令】
你必须扮演一个了解 Kahneman 行为经济学的分析师，在「行为金融」字段里覆盖：
1. 理性人检验：明确问"忘记成本，今天愿意以此价格买入吗？"
2. 识别可能存在的偏差：损失厌恶、锚定效应、FOMO、赌徒谬误、彩票心理（ST股尤其）
3. A股情绪温度：基于资金流向和最近价格波动，当前散户情绪是恐慌/贪婪/麻木？
4. 给出一句行为学视角的直接建议，不含糊，不两边讨好
```

**ST 股特殊处理（代码层）：**
- 股票代码/名称含 `ST`、`*ST` → `is_st = True` → 注入额外 prompt 上下文
- "退市概率高、流动性差、散户占比极高，是典型的彩票型资产，巴菲特会称之为 GRUESOME"

---

**Acceptance Criteria:**
- `analysis.behavioral` 字段非空，包含理性人检验问句
- ST股分析时，behavioral 字段包含退市风险提示
- 主力净流出超过 -10% 时，behavioral 字段包含资金出逃警告
- 分析结论为"卖出"时，behavioral 字段直接点名沉没成本谬误

---

---

### US-35 · PE/PB 历史百分位（估值定位）

**As a** 用户  
**I want to** 看到一只股票的 PE/PB 不只是当前值，而是在历史上处于什么位置  
**So that** 我能判断"现在贵不贵"，而不是只看一个孤立数字

**实现方案：**
- 数据源：AKShare `stock_a_lg_indicator_lgbm` 或 `stock_zh_valuation_baidu`，拉近 5 年历史 PE/PB
- 计算：`percentile = (当前值在历史序列中的排名) / 总数 × 100`
- 存储：`analysis` 表新增 `pe_pct` / `pb_pct` 字段（0-100 整数）
- 展示：详情页估值区块加一个小分位条 `▓▓▓▓░░░░ 73分位`，卡片信号栏加 `PE 73%位`

**分位解读标准（注入 prompt）：**
- < 20%：历史低估区，"比过去80%的时候都便宜"
- 20–50%：合理偏低
- 50–80%：合理偏高
- > 80%：历史高估区，"比过去80%的时候都贵，需要更高的成长来支撑"

**Acceptance Criteria:**
- 每次运行 pipeline 时更新 pe_pct / pb_pct
- 详情页估值 tab 显示分位条和文字解读
- 巴菲特信中估值判断引用分位数据（"当前 PE 在历史第 73 分位"）
- 数据缺失时优雅降级（不影响其他分析）

---

### US-36 · 新闻 → 持仓影响标注

**As a** 用户  
**I want to** 看新闻时直接知道哪条和我的持仓有关，以及影响是正面还是负面  
**So that** 我不需要自己判断每条新闻是否跟我有关

**实现方案：**
```
新闻原文 → LLM 提取结构化字段：
  - affected_codes: ["600519", "000858"]  # 相关股票代码
  - direction: "利空" | "利多" | "中性"
  - dimension: "政策" | "需求" | "成本" | "竞争" | "管理层" | "行业"
  - confidence: 0-1
```
- 只对用户自选股列表内的股票做交叉匹配（不做全市场扫描）
- 匹配到持仓时：新闻条目旁显示 `⚠ 影响你的持仓` 或 `↑ 利好你的持仓`
- 按影响强度排序（高置信度的相关新闻优先展示）

**新闻维度分类（注入 prompt 的判断框架）：**
- **行业性**（政策/宏观）：影响护城河判断，是长期变量 → 标注"行业影响"
- **公司性**（业绩/人事/并购）：直接影响评级 → 触发"建议重新分析"提示
- **市场情绪性**（大盘/资金面）：只影响时机，不影响公司价值 → 标注"情绪波动"，行为经济学层处理

**Acceptance Criteria:**
- 新闻爬取后异步跑标注 pipeline（不阻塞主流程）
- 首页/自选股页，有影响标注的新闻卡片有视觉区分
- 标注置信度 < 0.5 的不展示标注（只展示新闻本身）
- 公司性新闻触发"建议重新分析"提示，用户可一键触发

---

### US-37 · 持仓成本注入分析（个性化买卖建议）

**As a** 用户  
**I want to** 分析结果考虑我自己的买入成本，直接告诉我"以你的成本，现在该怎么做"  
**So that** 我得到的不是泛泛的"持有"，而是"你买在18元，现在22元，当前估值情况下的操作建议"

**实现方案：**
- `user_watchlist.buy_price` 已有，`pipeline` 里注入 prompt：
  ```
  用户买入价：¥18.00（当前浮盈 +22.2%，持有 87 天）
  ```
- 分析信 prompt 新增段落：
  ```
  【个人化建议】
  基于用户的买入成本和持有天数，给出具体的持仓建议：
  - 若浮盈超过 30%：讨论是否已超过内在价值，是否应部分止盈
  - 若浮亏超过 20%：直接做理性人检验，过滤沉没成本情绪
  - 若接近成本价：讨论"继续持有的理由是否仍然成立"
  ```
- 没有买入价时：跳过这段，降级为通用分析

**Acceptance Criteria:**
- `buy_price` 非空时，巴菲特信开头提及买入价和当前浮盈/浮亏
- 浮亏 > 20% 时必须出现理性人检验问句
- 浮盈 > 30% 时分析讨论止盈可能性
- 没有买入价时分析质量不受影响（正常降级）

---

### US-38 · 业绩日历与催化剂追踪

**As a** 用户  
**I want to** 知道我持有的股票下次业绩公告是什么时候，有没有近期的解禁/股东大会等事件  
**So that** 我能提前预判风险时间点，不被突发事件打措手不及

**数据源：**
- AKShare `stock_notice_report`：重大事项公告
- AKShare `stock_em_dxsyl`：大宗交易 / 限售解禁日历
- AKShare 财报日期：`stock_financial_report_date_em`

**展示：**
- 自选股页面顶部"近期事件"横幅：`【7天内】美的集团 一季报 4月28日`
- 详情页"事件"tab（新增）：完整的未来事件时间线
- 距今 ≤ 7 天的事件显示红点提醒

**Acceptance Criteria:**
- 每日 launchd 任务更新事件日历
- 自选股页有"近期事件"提醒条（有则显示，无则不占位）
- 详情页事件 tab 展示未来 90 天的事件列表
- 解禁事件特别标注解禁规模（大规模解禁 = 抛压风险）

---

### US-39 · 组合表现 vs 沪深300（基准比较）

**As a** 用户  
**I want to** 在算账页看到我的整体持仓表现跟沪深300指数的对比  
**So that** 我能知道自己选股是否真的跑赢大盘，还是还不如买 ETF

**实现方案：**
- 沪深300当日收盘价：AKShare `stock_zh_index_daily`（代码 `sh000300`）
- 对比维度：
  - 用户持仓加权平均收益率 vs 同期沪深300涨跌幅（按持有起始日计算）
  - 胜率：有买入价的股票中，跑赢同期沪深300的占比
- 算法：TWRR（时间加权收益率）——消除资金进出时点影响

**展示（算账页新增）：**
```
你的判断力 vs 大盘
持仓加权收益   +8.3%
同期沪深300    +5.1%
超额收益       +3.2% ✓ 跑赢大盘
```

**Acceptance Criteria:**
- 算账页底部新增"vs 大盘"模块
- 至少有 1 只有买入日期的持仓才显示（否则显示"数据不足"）
- 沪深300基准取每只持仓的买入日到今天的区间收益（不是单一时间点）
- 跑输大盘时不隐藏，直接显示负超额收益

---

---

### US-40 · 技术支撑位 + 筹码成本区（给妈妈看"这价格有没有托"）

**As a** 普通投资者（妈妈）  
**I want to** 在股票详情页看到当前价格相对于支撑位和机构成本区的位置  
**So that** 我能判断现在买/持有的价格是否安全，跌下去有没有人接

**数据层：**

| 指标 | 计算方法 | AKShare 接口 |
|------|----------|-------------|
| MA20 / MA60 / MA250 | 近 N 日收盘价均值 | `stock_zh_a_hist(adjust="qfq")` 取近 260 条 |
| 筹码密集区（上沿/下沿/峰值） | 筹码分布中占比最高的成本区间 | `stock_cyq_em(symbol, adjust="qfq")` |
| 当前价 vs 各支撑位距离 | `(price - MA) / MA * 100` | 由 annual 数据推算 |

**Pipeline 新增步骤 3.7：**
```python
def _fetch_technicals(code, market, log):
    # 仅 A 股；拉历史价格算 MA20/60/250；拉筹码分布取密集区
    # 存入 signals_json 的 technicals 子字典
```

**巴菲特信注入：**
```
【技术面参考】
当前价 ¥13.2，距 MA250（年线 ¥11.8）高 +11.9%，偏离较小，年线支撑有效。
筹码成本密集区：¥11.5–¥13.0（占全部筹码 38%），机构大户成本主要在此区间。
→ 当前价在筹码密集区上沿，有一定支撑，但继续上涨需要新增资金推动。
```

**展示（fundamentals 页新增一栏）：**
```
技术支撑位
  年线(MA250)  ¥11.8   当前高于 +11.9%
  半年线(MA120) ¥12.4   当前高于 +6.5%
  季线(MA60)   ¥13.0   当前高于 +1.5%  ← 近在咫尺

筹码成本密集区  ¥11.5 – ¥13.0（占38%）
  → 现价在密集区上沿，若跌入密集区有支撑
```

**Acceptance Criteria:**
- Pipeline step 3.7 拉取 MA20/60/250 并存入 signals_json.technicals
- Pipeline step 3.7 拉取筹码分布，提取峰值区间（最高密度的连续价格带，覆盖≥15%筹码）
- 巴菲特信 prompt 注入技术面段落（当前价与各 MA 的距离 + 筹码区间描述）
- fundamentals 页"技术支撑"栏展示（仅 A 股显示）
- 筹码 API 失败时降级，只显示均线，不报错

---

---

### US-41 · 交互体验修复（卡片点击 + 全选）

**As a** 用户  
**I want to** 点击卡片直接进详情、在我的选股页面移除股票、批量分析时能一键全选  
**So that** 操作流程更顺手，不需要找专门的"详情"按钮，也不用一个个勾选

**改动清单：**

| 位置 | 改动 |
|------|------|
| 首页卡片 | 点击卡片任意位置（避开按钮）→ 跳转详情页 |
| 首页卡片 | 去掉"详情 →"按钮、"移除"按钮、底部分析日期（均为冗余信息） |
| 我的选股页批量栏 | 进入选择模式后底栏新增"全选"按钮，已全选时切换为"取消全选" |
| 我的选股页批量栏 | 退出选择模式时"全选"按钮文字自动重置 |

**Acceptance Criteria:**
- 首页点卡片空白区域跳详情，点"读信"/"立即分析"等按钮不跳转
- 首页卡片不再显示"详情"和"移除"按钮
- 选择模式底栏有"全选"，点一次全勾，再点变"取消全选"全取消
- 退出选择模式后"全选"状态重置

---

### US-42 · 个性化首页日报（持仓 × 宏观合并简报）

**As a** 用户（妈妈 / 老师）
**I want to** 打开首页直接看到一份针对我持仓的今日简报——宏观发生了什么、我的持仓各自需不需要留意、巴菲特给我一句总结
**So that** 我不需要逐只打开详情页，首页本身就回答了"今天我该做什么"

---

**首页布局（有持仓时）：**

```
私人巴菲特 · Personal Buffett          2026年4月7日 · 星期二
──────────────────────────────────────────────────────
[今日简报]  最近更新：今天 16:05 CST               [↻ 刷新宏观]
──────────────────────────────────────────────────────
宏观一句话   大盘情绪恐慌，北向持续流出，关注防守型持仓。        ← A股
             Fear&Greed 38（恐惧），NZX50 -1.2%，关注防守。      ← NZ/US

你的持仓今天
  ⚠ 阳光电源   近3日跌破MA60，需留意              [查看详情]
  ✓ 三一重工   资金轻微流入，估值合理，持有         [查看详情]
  ✓ 长江电力   抗跌防守型，宏观下行期首选持有       [查看详情]

巴菲特说：   [3句话个性化总结，中文（妈妈）/ 英文（老师）]
──────────────────────────────────────────────────────
▼ 宏观数据详情（可折叠展开）
  A股三大指数 | 北向资金 | CNY/USD          ← cn region
  NZX50 | Fear&Greed | USD/NZD            ← nz region
──────────────────────────────────────────────────────
[新闻流]  本地新闻 / 国际新闻（两栏，US-19 样式）
```

---

**生成逻辑（不新增实时 LLM call）：**

| 触发时机 | 做什么 |
|---------|--------|
| 每日 launchd 16:00 CST（A股收盘后）| 跑完所有持仓分析 → 多一步 portfolio synthesis LLM call → 存 portfolio_analysis 表（linked to user_id）|
| 用户点「↻ 刷新宏观」| 只更新宏观数据（≤15秒）+ 重排持仓警示级别，**不重跑 LLM** |
| 当天没有简报时 | 显示昨日简报 + 小字"今日简报生成中" |

**Portfolio synthesis LLM call（每日一次）：**
- 输入：所有持仓的最新 analysis_results（结论/评级/behavioral hint）+ 当日宏观数据
- 输出：① 宏观一句话 ② 每只持仓的警示等级（⚠/✓/—）+ 一句话原因 ③ 巴菲特3句总结
- 语言：user.locale = zh → 中文；en → 英文
- 存入：portfolio_analysis 表，analysis_date = today，codes = 用户全部持仓

---

**信号集按 region 切换：**

| 信号 | cn（妈妈） | nz/us（老师 demo）|
|------|-----------|-----------------|
| 宏观一句话来源 | 北向资金 + 上证/深证/创业板 | Fear&Greed + NZX50 + USD/NZD |
| 持仓信号 | 主力资金 + MA60 偏离 + 估值分位 | PE vs 历史 + 评级变化 + FCF质量 |
| 隐藏字段 | — | 主力资金、北向、质押比例 |
| LLM prompt 语言 | 中文，巴菲特口吻 | English，Buffett letter style |

> 复用 US-27（教师版 demo）的 `locale=en + region=nz` 模式，无需额外改动。

---

**持仓警示级别判定（无需 LLM，规则引擎）：**

| 等级 | 触发条件 |
|------|---------|
| ⚠ 需留意 | 评级 C 以下 / 主力净流出 > 5% / 价格跌破 MA60 / behavioral 含"建议卖出" |
| ✓ 正常 | 评级 B 及以上 + 无触发条件 |
| — 无数据 | 当日无分析结果 |

---

**Acceptance Criteria:**
- 首页有持仓时，masthead 下方直接显示今日简报（不需要点按钮才出现）
- 「↻ 刷新宏观」按钮 ≤ 15秒，只更新宏观一句话 + 警示等级，不重跑 LLM
- 简报由 launchd 每日 16:05 CST 自动生成（A股收盘后5分钟），无需用户操作
- 宏观数据详情区块默认折叠，点击展开，不占首屏空间
- cn region：中文 + A股信号集；nz/us region：英文 + 国际信号集
- 无持仓时首页保持 US-14 设计（不显示简报区）
- portfolio_analysis 表按 user_id 存储，不同用户简报独立
- 新闻流（US-19）保留在简报下方，宏观数据详情和新闻都不删

---

### US-43 · 价值档案并入详情页 Tab（去掉独立页面）

**As a** 用户  
**I want to** 在股票详情页直接点「价值档案」Tab 就看到基本面数据，不跳转到另一个页面  
**So that** 浏览体验连贯，不需要在两个页面之间来回，手机上也不会失去上下文

---

**现状：**
- `/stock/<code>/fundamentals` 是独立页面，有自己的路由和模板
- 详情页（stock.html）Tab 栏里「价值档案 →」是一个外链，点了跳出去

**目标：**
- 把 fundamentals.html 的全部内容合并进 stock.html 的 Tab 内容区
- 去掉独立路由 `/stock/<code>/fundamentals` 和 fundamentals.html 模板
- Tab 栏「价值档案 →」变成真实 Tab（不带箭头），点击展开内容，不跳页

---

**Tab 内容区搬移清单（fundamentals → stock.html tab）：**

| 区块 | 现在在 fundamentals.html | 搬入 stock.html Tab |
|------|------------------------|-------------------|
| 盈利能力（ROE/净利率/ROIC/FCF） | ✅ | ✅ |
| PE/PB 历史百分位 + 偏贵/偏便宜标签 | ✅ | ✅ |
| 6年历年财务趋势表 | ✅ | ✅ |
| 护城河评估（moat_direction badge + reasoning） | ✅ | ✅ |
| Price Ladder（MA20/60/120/250 + VWAP，US-40） | ✅ | ✅ |
| 评级历史时间线 | ✅ | ✅ |

---

**路由变更：**
- 删除：`@app.route('/stock/<code>/fundamentals')`
- 删除：`templates/fundamentals.html`
- app.py `stock_fundamentals` 路由的数据查询逻辑迁移到 `stock_detail` 路由，合并返回
- 任何指向 `/fundamentals` 的链接（面包屑、股票卡片等）改为 `/stock/<code>#tab-fundamentals`

---

**Acceptance Criteria:**
- 详情页 Tab 栏「价值档案」点击后在同页展开内容，不跳转
- `/stock/<code>/fundamentals` 路由删除后返回 404 或重定向到详情页
- 所有 fundamentals 区块的数据、样式、功能与原独立页面一致
- 移动端 Tab 内容正常展示，不因内容增多导致布局破坏
- 面包屑不再出现「← 全部选股 / 价值档案」这种两级路径

---

---

### US-44 · 首页三卡片「影院感」重设计

**As a** 用户  
**I want to** 首页的三个功能卡片看起来像电影院场刊，大气、有层次感  
**So that** 打开 App 第一眼就觉得精致，不像普通小方格

---

**现状：**
- 三个小卡片（220px）横向滑动，背景都是白色带彩色左边框
- 视觉层次平，缺乏重量感，移动端像三个并排小按钮

**目标：**
- 卡片改为全宽（或接近全宽）垂直堆叠布局，不再横向滚动
- 每张卡片有明确的「主视觉区」：大标题 + 副内容，背景深浅对比
- 今日简报卡片最突出（最高，最先看到），我的选股次之，添加股票最矮
- 用已有颜色变量（`--ink`, `--ink-muted`, `--accent` 等），不新增配色
- 字体层次：主标题 18-20px bold，副标题 12px muted，数据 14px
- 卡片圆角、阴影与现有 UI 一致（border-radius 10px，subtle shadow）

**Acceptance Criteria:**
- 三卡片垂直堆叠，宽度铺满容器
- 今日简报卡片高度最大（约 100-120px），其余约 80px
- 没有横向滚动条
- 颜色只用已有变量
- 移动端与桌面端都正常

---

---

### US-45 · 分析系统架构重设计（数据层 × 分析层分离）

**As a** 用户
**I want to** 点「分析数据」和「更新新闻」是两个独立动作
**So that** 财务数据不需要每次重新爬，新闻可以按需更新，系统更快更准

**背景：**
- 现状：每次点分析都全量重爬（财报+新闻+价格），慢且浪费
- 财报数据是季度级，新闻是小时级，不应该同一个触发器

**数据分层：**
| 层级 | 内容 | 更新频率 | 触发方式 |
|---|---|---|---|
| 财务数据层 | ROE/净利率/ROIC/PE/PB/机构持仓 | 每季度 | 添加时 + launchd 季度 |
| 市场数据层 | 股价/成交量/主力资金/技术位 | 每天 | launchd 每日自动 |
| 新闻舆情层 | 新闻标题/情绪/来源 | 按需+1小时缓存 | 用户点「更新新闻」 |

**新闻缓存逻辑：**
- 用户点「更新新闻」→ 检查距上次抓取是否 < 1小时
- 是：直接用缓存 / 否：重新抓取，去重后追加到 stock_news 表
- 分析时取最近 7 天所有新闻（不只是刚抓的这批）

**前端两个按钮：**
- `[分析数据]`：用现有财务+市场数据跑定量评分 + 巴菲特信，不触发任何爬取
- `[更新新闻]`：按缓存规则决定是否重爬，输出新闻情绪摘要

**Acceptance Criteria:**
- `stock_news` 表建立，新闻按条追加不覆盖
- `[分析数据]` 响应时间 < 30s（因为不爬数据）
- `[更新新闻]` 1小时内重复点击直接返回缓存结果
- 两个分析结果可单独查看，也可合并进完整报告

---

### US-46 · 公司分类器（stock_meta）✅ 2026-04-13

**As a** 系统
**I want to** 在用户添加股票时自动判断公司类型、监管状态、市场层级，每季度重新校验
**So that** 不同类型的公司走不同的分析模型，ST/重整股不再错误地走巴菲特框架

**背景（真实案例触发）：**
- `*ST华闻 (000793)`：ST重整股被送进巴菲特框架，输出完全错误
- `九福来 (8611.HK)`：GEM股被误认为大陆传销公司，改名历史缺失导致背景判断出错

**公司类型（company_type）：**
| 类型 | 判断规则 | 分析模型 |
|---|---|---|
| `mature_value` | 稳定盈利，ROE > 10% | 巴菲特标准：ROE/护城河/FCF |
| `growth_tech` | 营收 CAGR > 20% 或科创板/GEM | 营收增速/毛利率/研发占比 |
| `financial` | 行业=银行/保险/券商 | ROA/净息差/不良率 |
| `cyclical` | 行业=钢铁/煤炭/化工/地产 | 周期位置/现金流/大宗价格 |
| `utility` | 行业=电力/水务/燃气 | 股息率/债务可持续性 |
| `pre_profit` | 连续2年以上亏损 | 现金 runway/营收增速 |
| `distressed` | ST/\*ST 状态 | 事件驱动框架（见 US-50） |

**ST 状态（st_status）— 触发框架路由的关键字段：**
- `NULL`：正常股票
- `ST`：财务异常，退市警告
- `*ST`：退市风险，重整/清算程序中
- `SST`：暂停上市

**市场层级（market_tier）：**
- A股：`main`（主板）/ `star`（科创板）/ `sme`（中小板）
- 港股：`main`（主板）/ `gem`（创业板，如九福来 8611.HK）
- 新西兰：`main` / `nxt`

**DB 变更 — `stock_meta` 表完整结构：**
```sql
CREATE TABLE stock_meta (
    code               TEXT PRIMARY KEY REFERENCES stocks(code),
    company_type       TEXT,                    -- 见上方枚举
    industry           TEXT,                    -- 行业分类
    market_tier        TEXT,                    -- 'main'|'gem'|'star'|'sme'|'nxt'
    st_status          TEXT,                    -- NULL|'ST'|'*ST'|'SST'
    st_since           TEXT,                    -- ST开始日期
    name_history_json  TEXT,                    -- [{name, from_date, to_date}]
    ipo_date           TEXT,
    total_shares       REAL,                    -- 总股本（亿）
    float_shares       REAL,                    -- 流通股本（亿）
    last_classified    TEXT,                    -- 上次分类时间
    manual_override    INTEGER DEFAULT 0,       -- 1=用户手动设置，不被自动覆盖
    updated_at         TEXT DEFAULT (datetime('now'))
);
```

**触发时机：**
- 用户首次添加股票时自动分类
- launchd 每季度重跑（财务变化可能改变类型；ST状态可能解除）
- `st_status` 变化时立即触发 US-50 框架路由更新
- 用户可手动覆盖（`manual_override=1` 保护，不被自动分类覆盖）

**Acceptance Criteria:**
- 添加股票后 `stock_meta` 有对应记录
- 000793 分类为 `distressed`，`st_status='*ST'`
- 8611.HK 分类为 `growth_tech`，`market_tier='gem'`，`name_history_json` 含 MINDTELL TECH 记录
- 分类结果（类型 + ST状态）显示在股票详情页头部
- Jupyter notebook `01_classify_watchlist.ipynb` 可跑出分类结果预览

---

### US-47 · ML 数据基础建设（建模埋点）

**As a** 未来的分析模型
**I want to** 现在开始积累干净的特征数据和标签数据
**So that** 以后可以训练自己的预测模型

**现在要埋的字段（feature）：**
- `feat_roe_trend`：ROE 近3年斜率（上升/下降/平稳）
- `feat_margin_stability`：净利率变异系数
- `feat_news_sentiment_7d`：近7天新闻情绪均值
- `feat_fund_flow_5d`：近5日主力资金累计净流入
- `feat_pe_percentile`：PE 在5年历史的百分位

**标签（label，事后回填）：**
- `label_7d_return`：分析后7日收益率
- `label_30d_return`：分析后30日收益率
- `label_beat_market`：是否跑赢沪深300

**工具：**
- Jupyter notebook `02_feature_exploration.ipynb`：探索特征分布
- scikit-learn 做基础分类（先用规则，积累数据后换 ML）

**Acceptance Criteria:**
- analysis_results 表有 feat_* 字段（已有，需确认是否填充）
- label_7d/30d 由 backfill_returns.py 每日回填
- notebook 能跑出特征相关性热力图

---

---

### US-48 · 数据验证层（Pipeline 前置检查）✅ 2026-04-13

**As a** 分析系统
**I want to** 在将数据送进 LLM 前进行合理性验证，并将异常数据明确标注
**So that** LLM 不再基于错误数据（如 PE 412x）生成误导性结论

**背景（真实案例）：**
- 佛塑科技 PE 412x 直接进入分析，巴菲特信基于此数据给出荒谬结论
- ROE 重复字段（TTM vs 年度）未去重，LLM 自行选择造成不一致

**验证规则：**
| 字段 | 异常条件 | 处理方式 |
|---|---|---|
| PE | > 150 | 标注"估值数据异常，跳过PE估值判断，改用PB" |
| PE | < 0 | 标注"当前亏损，PE无意义" |
| PE | 缺失 | 标注"PE数据缺失" |
| ROE | > 80% | 标注"ROE异常高，可能数据错误，谨慎参考" |
| ROE | 多个数据源冲突 | 标注"以最新TTM为准，历史年度数据仅参考趋势" |
| 负债率 | > 90% | 标注"财务杠杆极高，重点评估偿债能力" |
| 净利率 | < -50% | 标注"深度亏损，需关注现金流而非利润" |
| 价格 | 为0或NULL | 跳过技术分析；标注"价格数据缺失" |

**实现位置：** `scripts/pipeline.py` — `_run_analysis()` 之前插入 `_validate_signals()`

```python
def _validate_signals(code, signals) -> list[str]:
    """返回人类可读警告列表，注入分析 prompt"""
    warnings = []
    # ... 按上表检查
    return warnings
```

**DB 变更：**
```sql
CREATE TABLE data_quality_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT,
    field       TEXT,   -- 'pe_ratio'|'roe'|'debt_ratio' 等
    value       TEXT,   -- 原始值（字符串，兼容NULL/Inf）
    flag        TEXT,   -- 'outlier'|'missing'|'conflict'|'stale'
    reason      TEXT,   -- 人类可读说明
    logged_at   TEXT DEFAULT (datetime('now'))
);
```

**Acceptance Criteria:**
- PE > 150 时，巴菲特信中出现"估值数据存疑"字样，不基于该PE给出判断
- ROE 冲突时，信件明确标注"以TTM为准"
- `data_quality_log` 有对应异常记录，可在 Jupyter 里审查
- 验证逻辑不阻塞 pipeline，只是注入警告文本

---

### US-49 · 股票事件数据层（stock_events）✅ 2026-04-13

**As a** 分析系统
**I want to** 记录和查询影响股票价值的关键事件（重整进展/供股/改名/ST触发）
**So that** 事件驱动型股票（ST重整股）能基于真实进度而非财报做分析

**背景（真实案例）：**
- `*ST华闻 (000793)`：重整计划草案已出，表决日期未知，稀释比例未知——这些才是关键变量
- `九福来 (8611.HK)`：改名自 MINDTELL TECH，容易被误认为同名传销公司，改名时间线缺失

**事件类型枚举（event_type）：**
| 类型 | 说明 | 关键字段 |
|---|---|---|
| `st_trigger` | ST状态触发 | st_type, trigger_reason |
| `st_lifted` | ST解除 | lifted_date, reason |
| `restructuring_announced` | 重整计划公告 | plan_summary |
| `restructuring_vote` | 债权人/股东表决 | vote_date, vote_result |
| `restructuring_approved` | 法院裁定重整完成 | approved_date, dilution_ratio |
| `rights_issue` | 供股/配股 | ratio, price, record_date, pay_date |
| `bonus_share` | 转增股本 | ratio, record_date |
| `name_change` | 公司改名 | old_name, new_name, effective_date |
| `delist_warning` | 退市警示 | warning_date, reason |
| `delist_final` | 最终退市 | delist_date |
| `major_shareholder_change` | 大股东变动 | from_holder, to_holder, method |

**DB 变更：**
```sql
CREATE TABLE stock_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT REFERENCES stocks(code),
    event_type   TEXT NOT NULL,
    event_date   TEXT,           -- 事件发生/生效日期
    summary      TEXT,           -- 一句话摘要（注入 prompt 用）
    detail_json  TEXT,           -- 结构化数据，字段按 event_type 变化
    source       TEXT,           -- 'akshare'|'manual'|'cninfo' 等
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_stock_events_code ON stock_events(code);
CREATE INDEX idx_stock_events_type ON stock_events(event_type);
```

**数据来源（优先级）：**
1. AKShare `stock_notice_report`（公告）/ `stock_restructuring`（重整）
2. 巨潮资讯 cninfo.com.cn（A股公告）
3. 人工录入（UI上加"记录事件"入口）

**分析注入逻辑：**
- `_fetch_signals()` 中查询该股最近12个月的 `stock_events`
- 如存在 `restructuring_vote`，将表决日期和稀释比例注入分析 prompt
- 如存在 `name_change`，在分析开头注明"公司原名 XXX，与同名他公司无关"

**Acceptance Criteria:**
- `stock_events` 表建立，人工可录入事件
- 分析 000793 时，信件开头有重整进展摘要（如已录入事件）
- 分析 8611.HK 时，信件注明"原名 MINDTELL TECH"（如已录入改名事件）
- 事件列表显示在股票详情页"事件时间线"小区块

---

### US-50 · 分析框架路由（基于 stock_meta）✅ 2026-04-13

**As a** 分析系统
**I want to** 根据 `company_type` 和 `st_status` 自动选择对应的分析框架和 prompt 模板
**So that** ST重整股不再走巴菲特框架，金融股/周期股得到专属分析逻辑

**背景：**
这个软件的核心定位是"帮助学习复利的人，理解经济系统，找到对世界有利的方式"——
用同一套巴菲特框架分析所有股票，背离了这个定位。稳定复利股适合巴菲特，
但重整股是博弈，周期股是时机，金融股是杠杆，用同一把尺子量截然不同的东西。

**路由逻辑：**
```python
FRAMEWORK_MAP = {
    'distressed':   'event_driven',      # *ST/重整：关注事件进度、稀释风险、退出时间窗口
    'financial':    'bank_insurance',    # 银行保险：ROA/净息差/不良率/资本充足率
    'cyclical':     'cycle_position',    # 周期股：周期位置/库存周期/大宗价格趋势
    'utility':      'dividend_safety',   # 公用事业：股息率/债务可持续性/监管风险
    'growth_tech':  'growth_quality',    # 成长股：营收增速/毛利率扩张/研发效率
    'pre_profit':   'survival_check',    # 亏损早期：现金 runway/烧钱速率/催化剂
    'mature_value': 'buffett',           # 默认：ROE/护城河/FCF/安全边际
}
```

**各框架核心指标（注入 prompt 的不同部分）：**

**`event_driven`（ST重整）：**
- 重整计划完成度、债务减免比例、股权稀释比例
- 表决日期 → 是否还在时间窗口内
- 重整后存续公司的盈利能力预估
- 核心问题："重整能成功吗？成功后值多少？"

**`buffett`（价值股，现有逻辑）：**
- ROE/净利率/FCF/护城河/安全边际
- 保持现有巴菲特信格式

**`growth_quality`（成长/GEM）：**
- 营收 CAGR、毛利率趋势、研发占比
- 核心问题："护城河还在扩宽吗？现在的溢价值得付吗？"

**实现位置：** `scripts/buffett_analyst.py` — `analyze_stock_v2()` 接受 `framework` 参数

**DB 变更：**
- `analysis_results` 表加 `framework_used TEXT` 字段（记录本次分析用了哪个框架）

**Acceptance Criteria:**
- 分析 000793 时，`framework_used='event_driven'`，信件聚焦重整进度
- 分析 8611.HK 时，`framework_used='growth_quality'`，信件聚焦增长质量
- 分析 600519 时，`framework_used='buffett'`，格式不变
- 详情页头部显示"当前分析框架：[事件驱动 / 巴菲特 / ...]"
- 框架切换不影响现有分析结果的存储格式

---

---

### US-51 · 多用户推送路由（按持仓动态发送）

**背景**：现有 `stock_pipeline.py` 使用 `config.py` 里硬编码的 `WATCHLIST`，与 DB 的 `user_watchlist` 表完全脱节。系统有多个用户（admin、妈妈、其他），但每日推送不区分人、不区分持仓状态。

**目标**：pipeline 从 DB 读取各用户当前持仓，仅向「已开启每日推送」的用户发送其持仓相关报告。

**Acceptance Criteria**

1. pipeline 启动时，查询 `user_push_settings.notify_daily = 1` 的所有用户
2. 对每个推送用户，只抓取其 `user_watchlist.status = 'holding'` 的股票（非 watching/sold）
3. 抓取的股票池 = 所有推送用户持仓的并集（避免重复抓取）
4. 报告按用户过滤：每人只看到自己持仓的行情、新闻、分析
5. 推送渠道：优先读用户的 `discord_webhook` / `wecom_webhook`；若为空则回退到全局 env 变量
6. `bear_enabled = 1` 的用户额外保存到 Bear（目前只有 admin）
7. 硬编码的 `WATCHLIST` / `HK_WATCHLIST` 保留但仅作备用（当 DB 无持仓时 fallback）
8. 不改 DB schema，不改 web app 任何逻辑

**推送规则（妈妈）**
- 渠道：Server酱（`wecom_webhook` 字段存 Server酱 key）；不用 Bear，不用 Discord
- 有持仓：发「持仓报告」+ 「今日 A 级观察股」两部分
- 无持仓：只发「今日 A 级观察股」
- A 级观察股 = `user_watchlist.status='watching'` 且今日 analysis 评级 = 'A'

**不在范围内**
- 邮件推送；新建用户 UI

**技术路径**
- `stock_pipeline.py` `main()`：查 `notify_daily=1` 用户 → 取持仓并集抓数据
- `generate_report(allowed_codes)` 按 codes 过滤行情/新闻/分析
- 推送：`for user in push_users: send_serverchan(user.wecom_webhook, report)`

---

### US-52 · admin.py — 用户持仓 CLI 管理工具

**背景**：妈妈不用自己操作 web app，由管理员（周宇）在命令行维护她的持仓状态。

**命令设计**
```bash
python3 admin.py users                          # 列出所有用户
python3 admin.py watchlist <email>              # 查看某用户全部自选股
python3 admin.py set <email> <code> holding [--price 12.5] [--date 2026-01-01]
python3 admin.py set <email> <code> watching
python3 admin.py set <email> <code> sold [--price 15.0]
python3 admin.py add <email> <code>             # 添加股票到 watching
python3 admin.py remove <email> <code>          # 从自选股移除
python3 admin.py notify <email> on|off          # 开关每日推送
```

**Acceptance Criteria**
- 不依赖 Flask，直接操作 SQLite
- 输出表格对齐，中英文股票名都显示
- 操作前打印「将要做什么」，操作后打印「已完成」

---

### US-53 · 韩股支持（.KS 市场）

**背景**：韩国股票（如三星 005930.KS）无法搜索、添加、分析。

**Acceptance Criteria**
- `_detect_market("005930.KS")` → `"kr"`
- 搜索支持韩股代码（yfinance ticker 直接搜）
- pipeline 对 `.KS` 股票走 yfinance 抓行情 + 新闻（与 US 股票路径相同）
- 详情页显示 KRW 货币符号 ₩
- 分析框架：沿用 US 路径（yfinance financials）

---

### US-54 · 英文界面补全

**背景**：i18n en.json 缺大量 key，英文模式下很多地方显示中文或空白。

**Acceptance Criteria**
- 审查 `i18n/en.json` vs `i18n/zh.json`，补全所有缺失 key
- 模板里硬编码的中文文本提取到 i18n（主要页面：index、watchlist、stock）
- 不改功能，不改样式，只补翻译

---

### US-55 · 数据三层分离 + 新闻 on-demand 缓存

**背景**：目前 pipeline 一锅炖（财务/市场/新闻混跑），新闻每次都重爬，没有缓存保护，用户也无法单独触发新闻更新。

**设计目标**：把数据分成三层，各自有独立触发逻辑：

```
财务数据层  quarterly
  ROE / 净利率 / ROIC / PE / PB / 机构持仓
  触发：添加股票时 + 每季度 launchd

市场数据层  daily
  股价 / 成交量 / 主力资金 / 技术位
  触发：每天 launchd 自动跑（现有 pipeline）

新闻舆情层  on-demand + 1小时缓存
  新闻标题 / 情绪值 / 来源 / 发布时间
  触发：用户点「更新新闻」按钮
```

**新闻缓存逻辑**：
```
用户点 [更新新闻]
  ↓
距上次抓取 < 1小时？
  ├── 是 → 直接用 stock_news 表里已有数据分析
  └── 否 → 重爬 → 去重追加到 stock_news → 分析最近7天所有新闻
```

**Acceptance Criteria**

- [x] `app.py` 新闻缓存判断：`/api/refresh-news/<code>` POST 端点检查当日是否已有 ≥3 条新闻，有则跳过重爬（`run_news_update` 实现）
- [x] `/api/news/<code>` GET 端点：返回最近7天新闻（原为3天，已修复 2026-04-16）
- [x] `/api/refresh-news/<code>` POST 端点：单独触发新闻抓取（`start_news_update` → `run_news_update` → `_fetch_1c1_news`）
- [x] `stock.html` 「更新新闻」按钮：在 ⋯ 菜单里，调用 `/api/refresh-news/<code>`
- [x] 「巴菲特怎么看」只跑量化（`start_quant_only`），不重爬新闻
- [ ] 新闻分析结果单独展示区块（情绪趋势独立区块，不与巴菲特信混合）——当前新闻情绪显示在信号面板（US-63），但不是单独的"情绪趋势"图表

**已有基础（不用重建）**：
- `stock_news` 表已存在，schema 完整（`sentiment`、`fetched_at`、`category` 字段都有）
- `db.upsert_stock_news()` 和 `db.get_stock_news()` 已存在
- 新闻抓取逻辑在 `scripts/stock_pipeline.py` 的 `_fetch_news()` 里

---

### US-56 · 港股/美股财务数据补强

**背景**：港股（如 SMIC 0981.HK）分析质量明显低于 A股，原因是 yfinance 只提供基础字段，缺少多年趋势数据。SMIC 分析信里出现「债务比 35.97x」这种明显错误的数字（字段含义混淆）。

**问题清单**：
1. `debt_to_equity`（D/E ratio）被错误显示为「债务比」，数值不经换算直接展示
2. 港股/美股缺 5年 ROE/净利率趋势（只有单点快照）
3. 港股缺技术支撑位分析（MA/VWAP）
4. 分析信里出现 markdown 加粗（`**ROE 仅 2.96%**`），破坏信件格式

**Acceptance Criteria**

- [x] 修复 `debt_to_equity` 字段展示逻辑：D/E ratio > 5 时加 ⚠ 标注 + tooltip 说明（`debt_ratio_note`），页面标签改为"D/E 比率"（2026-04-16）
- [ ] 港股/美股 prompt 里明确告知 LLM「财务数据为单点快照，无历史趋势，分析时应降低置信度」
- [ ] LLM system prompt 加指令：禁止在信件正文里使用 markdown 加粗，保持散文格式
- [x] `_fetch_1b_financials()` 对非A股抓取 yfinance `income_stmt`（已实现3年净利率趋势计算，存入 annual_json）

---

### US-57 · Server酱 微信推送接入

**背景**：US-51 推送路由已完成 DB 驱动逻辑，但 `send_serverchan()` 函数是 stub，实际没发出去。妈妈的每日推送目前只到 Discord/Bear，不到微信。

**推送流程**
```
pipeline 结束
  ↓
对每个 notify_daily=1 用户
  ↓
  读 user_push_settings.wecom_webhook（存 Server酱 SendKey）
  ├── 有持仓 → 持仓简报 + 今日 A 级观察股
  └── 无持仓 → 仅 A 级观察股
  ↓
POST https://sctapi.ftqq.com/{SendKey}.send
  title: "巴菲特日报 {日期}"
  desp:  markdown 正文（股票列表 + 涨跌 + 评级 + 巴菲特一句话总结）
```

**Acceptance Criteria**

- [x] `stock_pipeline.py` 里真正实现 `send_serverchan(key, title, desp)`：POST 到 `sctapi.ftqq.com`，检查返回 `code=0` 确认发送成功
- [x] 推送内容格式（markdown）：紧凑表格（持仓表格 + 巴菲特说 + A 级观察股），`build_user_push_content` 已按此格式实现
- [x] 推送失败时 log warning，不影响主流程
- [x] 用 `admin.py push-key <email> <serverchan_key>` 设置 SendKey（写入 wecom_webhook 字段）
- [x] 在 `admin.py` 里加 `test-push <email>` 命令：发送一条测试消息验证 key 有效

**不在范围内**：企业微信机器人、模板消息、公众号推送

---

### US-58 · 北向资金数据修复

**背景**：pipeline 里有北向资金抓取逻辑（`_fetch_fund_flow` 或类似），但字段名核对从未完成。实际 AKShare 接口字段名已多次变更，导致北向资金数据可能一直是 NULL 或字段对不上。

**问题定位**
- AKShare `stock_hsgt_north_net_flow_in_em()` 或 `stock_em_hsgt_north_acc_flow_in()` 字段名不稳定
- 可能字段叫 `北向资金` 或 `净流入` 或 `value`，需要实际运行检查

**Acceptance Criteria**

- [x] 运行确认当前字段名：`stock_hsgt_fund_flow_summary_em()` 实际列为 `交易日/类型/板块/资金方向/成交净买额/资金净流入`（与原代码预期完全不同）
- [x] 修复 `stock_fetch.py fetch_north_bound()`：按 `资金方向=='北向'` 过滤，用 `板块` 区分沪/深股通，`资金净流入`（百万元）/100 得亿元，`交易日` 取日期
- [ ] 在至少一只持仓 A 股上验证：pipeline 跑完后 `signals.north_flow` 不为 None（需收盘后运行 pipeline 验证）
- [x] graceful fallback：`except Exception` 已捕获，返回空 dict，不中断 pipeline

---

### US-59 · 推送质量评分（避免发垃圾报告）

**背景**：当前推送不论分析质量如何都发出去。遇到 pipeline 超时 / LLM 失败 / 数据全 NULL 的情况，推送出去的是一封空壳报告，信息量为零，损害用户信任。

**设计**：推送前做质量门禁，低于阈值的报告不推送，改发「今日数据获取失败」摘要。

**质量评分规则（0-10分）**：
```
+3  有收盘价（price 不为 None）
+2  有巴菲特信（analysis_text 长度 > 200 字）
+2  有新闻（stock_news 当天有 ≥ 1 条）
+2  有评级（grade 不为 None）
+1  有财务数据（ROE 不为 None）
```

**Acceptance Criteria**

- [ ] `stock_pipeline.py` 加 `_score_report(stock_data) → int` 函数，按上面规则打分
- [ ] 推送逻辑：单股得分 < 5 时，从「持仓简报」里排除，移入「获取失败」列表
- [ ] 如果用户所有持仓得分都 < 5，今日推送改为：「{date} 今日数据获取失败，请稍后在 web 查看」
- [ ] 得分记录到 `analysis_results.data_quality_score` 字段（或 data_quality_log）
- [ ] 不影响 web 端展示（web 端可以展示低质量数据，推送端才有门禁）

---

### US-60 · 买入区间 + 止损位 UI 接入（===TRADE=== 解析）

**背景**：`_compute_trading_params` 已在 `pipeline.py` 里计算均线买入区间和止损位，并注入 LLM prompt。LLM 也被要求输出 `===TRADE===...===TRADE_END===` 结构块。但 `analyze_stock_v2` 的解析逻辑只处理 `===DIMS===`，TRADE 块目前混在 `letter_html` 里以原始文字渲染，没有独立的 UI 展示。

**行为层缺口**：
```
pipeline 计算 trading_params  ✅
→ 注入 LLM prompt              ✅
→ LLM 输出 ===TRADE=== 块      ✅（但混在信件正文里）
→ 解析提取 trade_block         ❌
→ 存入 DB                      ❌
→ stock.html 专属卡片展示       ❌
```

**Acceptance Criteria**

- [x] `buffett_analyst.py` `analyze_stock_v2` / `analyze_stock_v3` 解析 `===TRADE===...===TRADE_END===` 块，存为独立字段 `trade_block`
- [x] 返回 dict 里有 `"trade_block": trade_block`
- [x] `db.py` `save_analysis()` 动态列写入，`analysis_results` 表已有 `trade_block TEXT` 列（migrate 时自动 ALTER）
- [x] `db.py` `get_latest_analysis()` 返回 `trade_block`（SELECT * 包含全部列）
- [x] `app.py` `stock_page` 无需单独传参——`analysis` dict 里已含 `trade_block`，`stock.html` 直接读 `analysis.trade_block` ✅
- [x] `stock.html` 「操作参数」卡片已实现，当 `analysis.trade_block` 存在时渲染
- [x] 卡片样式：灰色边框，小字；标注「数据不构成投资建议」
- [x] `distressed / speculative` 不显示操作参数卡片
- **Bug fix（2026-04-16）**：`run_letter_only` 的 `save_analysis` 调用漏传 `trade_block`，已补上

**DB Migration**：
```sql
ALTER TABLE analysis_results ADD COLUMN trade_block TEXT;
```

---

*最后更新：2026-04-16（US-55/56/60 状态修正；bug fix 批次）*


---

## US-61 · 分析与股东信解耦（Groq 限速缓解）

**背景**：当前「巴菲特怎么看」一个按钮串联定量评级（~3s，无 LLM）和股东信生成（~30s，Groq），Groq 限速或超时会让整个流程卡住。

**目标**：把两件事拆成两个独立操作，用户先看到数据驱动的评级，按需再生成叙事信件。

**Acceptance Criteria**

- [ ] `pipeline.py` 新增 `run_quant_only()` / `start_quant_only()`：只跑 `_run_layer2()`（量化评级），不调用 Groq，~3s 完成
- [ ] `pipeline.py` 新增 `run_letter_only()` / `start_letter_only()`：从 DB 重建 `quant_result`，只调用 `analyze_stock_v3()`（Groq），仅更新 `letter_html` / `fund_flow_summary` / `behavioral` 等叙事字段，不覆盖 `grade`/`conclusion`
- [ ] `app.py` `/api/analyze-only/<code>` 改为调用 `start_quant_only()`（原 start_analysis_only 不再走 Layer 3）
- [ ] `app.py` 新增 `/api/generate-letter/<code>` POST 端点，调用 `start_letter_only()`，返回 `{job_id}`
- [ ] `stock.html` 「巴菲特怎么看」按钮行为不变，但背后只跑量化，~3s 刷新页面
- [ ] `stock.html` 在今日简报底部新增「读股东信」按钮：若 `letter_html` 已存在则直接弹 Modal；若无则调 `/api/generate-letter` 并显示 spinner，完成后自动弹窗
- [ ] `stock.html` 原「读巴菲特信」按钮（在 brief-header 里）合并为同一逻辑

*最后更新：2026-04-15（新增 US-61）*

---

## US-62 · Pipeline 层级重构：1a/1b/1c1/1c2/1c3 + 2 + 3

**背景**：当前 pipeline 的 Layer 1（数据爬取）是个大杂烩，价格/财务/新闻/资金/技术面全部混在一起，导致：
- 任何一个数据源挂掉会影响整个分析
- 无法按需刷新（比如只想更新价格，不重爬财务）
- 不同市场（A股/美股/港股）的可用数据不同，但代码没有分支
- 维护时需要读完整个函数才能定位问题

**目标**：把 Layer 1 拆成 5 个独立、可单独调用的子层，每层有自己的缓存策略和市场路由。

---

### 层级定义

```
Layer 1a  行情层     价格/涨跌/成交量/市值         ~0.5s  不缓存（每次都要最新）
Layer 1b  财务层     ROE/利润率/FCF/资产负债/PE/PB  ~5s    缓存7天（季报才变）
Layer 1c1 新闻情绪层 新闻标题+摘要+情绪打分         ~3s    缓存24h
Layer 1c2 资金信号层 北向资金/主力买卖/机构持仓      ~3s    缓存24h（A股专属，其他市场跳过）
Layer 1c3 技术面层   历史K线/MA20~250/VWAP60/120    ~2s    缓存24h
──────────────────────────────────────────────────────────
Layer 2   定量评级   读DB纯计算，无网络调用          ~1s
Layer 3   LLM叙事    Groq生成股东信                 ~30s   按需
```

---

### 各层市场覆盖

| 层 | A股(CN) | 美股(US) | 港股(HK) | NZ股(NZ) | 韩股(KS/KQ) |
|----|---------|---------|---------|---------|------------|
| 1a | ✅ Sina hq | ✅ yfinance | ✅ yfinance | ✅ yfinance | ✅ yfinance |
| 1b | ✅ AKShare | ⚠️ yfinance 基础 | ⚠️ yfinance 基础 | ⚠️ yfinance 基础 | ⚠️ yfinance 基础 |
| 1c1 | ✅ Google News | ✅ Google News | ✅ Google News | ✅ Google News | ✅ Google News |
| 1c2 | ✅ 新浪/AKShare | ❌ 跳过 | ❌ 跳过 | ❌ 跳过 | ❌ 跳过 |
| 1c3 | ✅ 新浪K线 | ✅ yfinance history | ✅ yfinance history | ✅ yfinance history | ✅ yfinance history |

---

### 触发组合（对应前端按钮）

| 触发场景 | 跑哪些层 | 预计时间 |
|---------|---------|---------|
| 「巴菲特怎么看」(日常) | 1a + 1c1 + 1c2 + 2 | ~5s |
| 「完整分析」(首次/季报后) | 1a + 1b + 1c1 + 1c2 + 1c3 + 2 | ~15s |
| 「刷新行情」 | 1a only | ~1s |
| 「生成股东信」 | 3 only | ~30s |
| 定时每日任务 | 1a + 1c1 + 1c2 + 2 | ~5s/只 |

---

### 代码结构目标

```python
# pipeline.py 目标结构

def _fetch_1a_quote(code, market):     """行情层：价格/涨跌/成交量"""
def _fetch_1b_financials(code, market): """财务层：ROE/利润率/FCF（含7天缓存判断）"""
def _fetch_1c1_news(code, market):     """新闻情绪层：抓取+情绪打分（含24h缓存）"""
def _fetch_1c2_capital(code, market):  """资金信号层：北向+主力（仅A股，含24h缓存）"""
def _fetch_1c3_technicals(code, market):"""技术面层：历史K线+MA/VWAP（含24h缓存）"""

def _run_layer2(code, market, log, user_id):  """定量评级：读DB纯计算（现有，保留）"""
def run_letter_only(...)                      """LLM叙事（现有，保留）"""
```

---

### 缓存策略（DB 实现）

在 `fundamentals` / `signals` 表上加 `fetched_at` 时间戳字段。
每个子层在爬取前检查：
```python
def _should_refresh_1b(code) -> bool:
    last = db.get_financials_fetched_at(code)
    return last is None or (now - last).days >= 7

def _should_refresh_1c1(code) -> bool:
    last = db.get_news_fetched_at(code)
    return last is None or (now - last).hours >= 24
```

---

**Acceptance Criteria**

- [ ] `pipeline.py` 按上述结构拆分为 5 个独立 `_fetch_*` 函数，每个函数只负责自己那层
- [ ] 每个 `_fetch_*` 函数开头有市场路由：不支持的市场直接 `return`（不报错）
- [ ] 缓存逻辑内置在每个函数里，外部调用无需关心
- [ ] `run_quant_only()` 改为触发 1a + 1c1 + 1c2 + Layer2
- [ ] 新增 `run_full_analysis()` 触发所有子层 + Layer2（首次/完整分析用）
- [ ] DB 各相关表加 `fetched_at` 字段
- [ ] 每个函数有独立的错误捕获，一层失败不影响其他层

---

## US-63 · 新闻+信号 Tab 重设计（1c1/1c2/1c3 合并呈现）

**背景**：当前「新闻」tab 只显示新闻列表。1c2（资金信号）和 1c3（技术面）的数据散落在「档案」tab 里，没有独立的视觉区块。用户想一眼看到「今天有什么信号」。

**目标**：把「新闻」tab 升级为「信号+新闻」tab，三类信号放在前面，新闻链接往下放。

---

### UI 布局（新闻 tab 内部）

```
┌─ 📡 今日信号 ────────────────────────────────────┐
│                                                   │
│  [资金信号]  仅A股显示                             │
│  北向资金：净流入 +12.3亿  📈                      │
│  主力动向：小幅净买入  ➖                           │
│  机构持仓：Q1末增持 +2.3%  📈                     │
│                                                   │
│  [技术信号]  所有市场                              │
│  当前 ¥45.2 在 MA60(43.1) 上方，距年线MA250 +8%   │
│  VWAP60: ¥44.8 / VWAP120: ¥43.2                  │
│  位置判断：中间区域，未到极端超买/超卖              │
│                                                   │
│  [新闻情绪]  所有市场                              │
│  本周 8 条新闻：📈 5 正面  ➖ 2 中性  📉 1 负面    │
│                                                   │
└───────────────────────────────────────────────────┘

─── 新闻列表 ──────────────────────────────────────
📈 标题一  来源  时间
➖ 标题二  来源  时间
...
```

---

### A股 vs 非A股差异

**A股**：显示资金信号 + 技术信号 + 新闻情绪（全部）
**美股/港股/NZ/韩股**：隐藏资金信号区块，显示技术信号 + 新闻情绪

---

**Acceptance Criteria**

- [ ] 「新闻」tab 顶部新增「今日信号」卡片区
- [ ] 资金信号区：market=cn 时显示北向/主力/机构数据，非CN市场隐藏整个区块
- [ ] 技术信号区：所有市场显示，显示 MA60/MA250 位置判断 + VWAP60/120
- [ ] 新闻情绪区：显示本周新闻情绪分布统计（正/中/负计数）
- [ ] 原新闻列表保留，移至信号卡片下方
- [ ] 各区块数据不存在时显示「数据积累中」，不报错不崩溃

---

## US-64 · 市场差异化分析框架（不同市场不同数据方案）

**背景**：目前 A股分析是完整的（5层数据），但美股/港股/NZ 缺少 1c2（资金信号），1b（财务）也偏弱。代码没有明确的市场分支，导致非A股分析结果质量参差不齐，用户看到一堆「数据积累中」。

**目标**：为每个市场定义明确的「能提供什么数据」，LLM prompt 和 UI 根据实际可用数据动态调整，不展示根本没有的东西。

---

### 各市场数据能力矩阵

| 能力 | A股(CN) | 美股(US) | 港股(HK) | NZ(NZ) | 韩股(KS/KQ) |
|------|---------|---------|---------|--------|------------|
| 实时行情 | ✅ Sina | ✅ yfinance | ✅ yfinance | ✅ yfinance | ✅ yfinance |
| PE/PB | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| ROE/利润率趋势 | ✅ AKShare | ⚠️ yfinance | ⚠️ yfinance | ❌ | ❌ |
| FCF/ROIC | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |
| 北向资金 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 主力资金 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 机构持仓 | ✅ | ✅ SEC | ⚠️ | ❌ | ❌ |
| 技术面(MA/VWAP) | ✅ | ✅ | ✅ | ✅ | ✅ |
| 新闻 | ✅ | ✅ | ✅ | ✅ | ⚠️ |

---

### LLM Prompt 市场路由

```python
MARKET_ANALYSIS_CAPS = {
    "cn": ["quote", "financials_full", "capital_flow", "technicals", "news"],
    "us": ["quote", "financials_basic", "technicals", "news"],
    "hk": ["quote", "financials_basic", "technicals", "news"],
    "nz": ["quote", "technicals", "news"],
    "ks": ["quote", "financials_basic", "technicals", "news"],
}
```

LLM prompt 根据市场自动调整：
- CN：全量 prompt，包含北向/主力/机构分析指令
- US/HK：省略资金流向章节，加强护城河/估值分析
- NZ：只有行情+新闻，prompt 强调「数据有限，判断谨慎」

---

**Acceptance Criteria**

- [ ] `pipeline.py` 加 `MARKET_ANALYSIS_CAPS` 字典，各市场声明可用能力
- [ ] `_fetch_1c2_capital` 在非CN市场直接 `return {}`，不尝试调用
- [ ] `buffett_analyst.py` 根据 `market` 和实际可用数据动态裁剪 system prompt
- [ ] `stock.html` 信号区块根据 market 决定显示哪些数据项（非CN隐藏资金信号）
- [ ] 当某层数据缺失时，UI 显示「该市场暂不支持此数据」而非空白或报错
- [ ] CLAUDE.md「市场覆盖表」更新为与 `MARKET_ANALYSIS_CAPS` 一致

---

---

## US-65 · 差评预警：连续 6 次 D/D- 提醒移除

**背景**：巴菲特说「发现自己在烂公司里，最好的办法是赶快离开」。与其让差公司长期占据自选股位置，不如让系统主动提醒用户审视是否值得继续跟踪。

**规则**：某只股票最近 6 次分析评级**全为 D 或 D-**，且该股票**不在持有区（status != 'holding'）**，则向用户发送一次提醒。

**方案 C（通知 + 手动确认）**：系统只提醒，不自动删。用户主动选择移除或继续观察。

---

### 触发逻辑

```
分析完成后 → 查该股票最近 6 条 analysis_results（period=daily）→
若 6 条都存在且 grade 全为 D/D- →
检查 user_notifications 里是否已有未处理的同类提醒 →
没有则插入新提醒
```

**注意**：
- 只检查当前用户自选股里的股票（`user_watchlist`）
- 持有区（`status='holding'`）不触发（还拿着仓位，需手动决策）
- 用户点「继续观察」后，该股票 **60 天内不再触发**同类提醒

---

### 数据层

新表 `user_notifications`：

```sql
CREATE TABLE IF NOT EXISTS user_notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    code         TEXT,
    type         TEXT,          -- 'poor_rating'
    message      TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    snoozed_until TEXT,         -- 「继续观察」时设置 60 天后日期
    dismissed_at TEXT           -- 「移除」或手动关闭时设置
);
```

---

### UI

**我的选股页（watchlist.html）顶部横幅**（仅有未处理提醒时显示）：

```
⚠️  2 只股票已连续 6 次评为 D 级    [查看详情 ↓]
```

展开后每条提醒显示：
- 股票名 + 代码
- 最近 6 次评级时间线（小标签）
- [移除自选股] [继续观察 60 天] 两个按钮

---

### Acceptance Criteria

- [ ] 新增 `user_notifications` 表（`db.py`）
- [ ] `db.py` 加 `check_poor_rating_streak(code, user_id)`：查最近 6 条评级，全为 D/D- 且非持有区则返回 True
- [ ] `db.py` 加 `create_notification` / `get_active_notifications` / `snooze_notification` / `dismiss_notification`
- [ ] `pipeline.py` 分析完成后调用检查，触发则写入通知
- [ ] `app.py` `/watchlist` 路由传入 `notifications` 列表
- [ ] `app.py` 加 `/api/notification/<id>/snooze` 和 `/api/notification/<id>/dismiss` 端点
- [ ] `watchlist.html` 顶部显示提醒横幅，展开显示详情 + 操作按钮
- [ ] 持有区股票不触发

---

*最后更新：2026-04-16（US-55/56/60 状态修正；bug fix 批次；新增 US-66）*

---

## US-66 · 财务指标通俗解读（数据 + 意义）✅ 2026-04-16

**As a** 非专业投资者
**I want to** 每个财务数字旁边有一句人话解释"这意味着什么"
**So that** 我不需要懂金融就能判断这家公司的钱赚得怎么样

**实现：** 纯规则引擎，无 LLM，`_compute_metric_hints()` in `app.py`，`metric_hints` 传模板。中/英文根据 `session.locale` 自动切换。

| 指标 | 逻辑简述 |
|---|---|
| PE | <15 不贵，15-25 合理，25-40 市场认为它还会继续增长，>40 在赌高速增长，<0 亏了 |
| ROE | <0 亏了，<5% 不如存银行，5-10% 一般，10-20% 不错，≥20% 很能赚 |
| 净利润率 | <0 亏了，<5% 一出问题就垮，5-10% 辛苦钱，10-20% 不错，≥20% 挣钱轻松 |
| 负债率(A股%) | <40% 借得少，40-70% A股常见，70-90% 借了很多，>90% 一出问题就垮 |
| D/E(非A股) | ≤1 稳健，1-3 可控，3-10 一出问题就垮，>10 一出问题就垮 |
| ROIC | <8% 不如买沪深300，8-15% 还行，≥15% 很划算 |
| FCF | ≥0.8x 钱真的进了口袋，0.3-0.8x 尚可，<0.3x 账面有钱但没进口袋 |

**Acceptance Criteria:**
- [x] 6个核心指标每个有解读文字，≤25字，口语化，无专业术语
- [x] 颜色：好=绿，一般=灰，差=红；复用 `--green` / `--red` CSS 变量
- [x] 中英文根据用户 locale 自动切换（`session.locale`）
- [x] 数据缺失时不显示解读，不报错
- [x] 移动端正常，不撑高卡片

---

## US-67 · 提问箱

**As a** 测试用户（妈妈/朋友）
**I want to** 随时问一个关于股票或 app 的问题，马上得到回答
**So that** 我不需要等人工回复，同时我的问题也帮助产品团队了解用户真正想要什么

**核心洞察**：用户以为在用 AI 问答助手；产品团队实际上在收集用户真实需求。每一条问题都是产品调研数据。

### 前端

**悬浮入口**：所有登录页面右下角，固定定位。
- 图标：小纸条气泡形状（💬 style，非圆形 bot）
- 无文字标签，hover 显示 tooltip「有问题？问问看」
- 点击弹出聊天气泡面板（不跳转页面）

**聊天气泡面板**（右下角展开，像 iMessage 小窗）：
- 顶部：「提问箱」标题 + 关闭按钮
- 对话区：显示历史问答（本 session 内）
- 开场白（灰色气泡）：「有什么不明白的，直接问吧 📝」
- 底部输入框 + 发送按钮
- 用户发问 → 显示用户气泡（右对齐）→ 加载中「...」→ Groq 回答气泡（左对齐）
- 面板宽 320px，移动端全宽

### 后端

**API**：`POST /api/ask`
- 接收 `question`（必填，最多300字）
- 调用 Groq（`llama-3.3-70b-versatile`，max_tokens=400）
  - System prompt：「你是一个友好的股票投资助手，帮助普通投资者理解股票数据和投资概念。用简洁口语化的中文回答，不超过150字。」
- 将 `(user_id, question, answer, created_at)` 存入 `user_questions` 表
- 返回 `{"answer": "..."}`

**DB**：`user_questions` 表
```
id          INTEGER PRIMARY KEY
user_id     INTEGER
question    TEXT
answer      TEXT
created_at  TEXT DEFAULT (datetime('now'))
```

**Admin 端**：`/admin/questions`（admin only）
- 按时间倒序列出所有问题 + 回答
- 显示提问用户（email/display_name）
- 未读（24h内）高亮显示

### Acceptance Criteria
- [ ] 所有登录页面右下角有悬浮气泡入口
- [ ] 点击弹出聊天面板，不跳转不刷页
- [ ] 用户发问 → Groq 回答，流程 ≤15s
- [ ] 问答自动存入 `user_questions` 表
- [ ] `/admin/questions` 展示所有问答记录
- [ ] 移动端面板正常，不遮挡主要操作区域
- [ ] Groq 失败时显示「暂时无法回答，稍后再试」，不报错
