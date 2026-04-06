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

*本文档由 Claude Code 起草，最终以用户确认版本为准。*
*最后更新：2026-04-07*
