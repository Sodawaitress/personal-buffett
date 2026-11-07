# US-228 财报卡 · 调研与设计（2026-11-08）

> 实现会在另一台电脑上做，这份是交接用的设计稿。标 ⚠️ 的是二手摘要，没读原文；引用前要核实。

## 一、别人怎么做

| 产品 | 做法 | 可借鉴 | 不足 |
|---|---|---|---|
| **Robinhood** | 股票页有 Earnings 区：最近几个季度「预期 EPS vs 实际 EPS」，下次财报日期，可以听电话会（官方帮助页） | 下次财报日期 + 预期对实际，放在股票页上 | 只有 EPS 一个数，不解释意味着什么 |
| **moomoo / 富途** | AI 财报工作流分三段：财报前锚定预期，财报期间几分钟内提取核心数据，财报后分析趋势；把公司自己的关键指标（例：特斯拉交付量）和前几个季度画成图对比（官方营销页 ⚠️）；需要开交易账户才能用 | **前·中·后三段**；**公司专属指标的季度序列** | 营销性质，具体效果没验证 |
| **Fiscal.ai / YCharts** | 收集 2,000+ 家公司的「分部 + 公司专属 KPI」 | 用户评价里最被看重的就是 KPI 数据，别家很少有 ⚠️ | 专业工具，付费 |
| **Simply Wall St** | 自动生成财报短讯：「收入 11.4 亿美元，同比 +32%；EPS 超预期 8.5%」 | 一句话报数字 | 只报数字，不讲意味着什么、市场为什么这样反应 |

**共同点**：几乎都围绕「EPS 超没超分析师预期」。**共同的缺口**：很少有产品用大白话解释「这次财报说明了什么、和公司自己的故事对不对得上」。这正好是本站的位置。

## 二、学界告诉我们什么

1. **股价反应的是「超出预期的部分」，不是数字本身**（经典结论，Ball & Brown 1968 以来的财报研究传统）→ 卡片必须有一个**比较基准**。分析师一致预期要付费，但**公司自己上一季给过指引**（DUOL Q2 信里写了 Q3 bookings 指引 $307M，实际 $316.1M），这个基准免费、公开、可核对
2. **指引比当季数字更要紧，而且坏消息的分量更重**：Rees & Twedt（2011）发现，下调指引带来的股价惩罚，明显大于「超预期」带来的奖励 ⚠️ → 指引上调 / 维持 / 下调要放在显眼位置，写出旧数字→新数字
3. **LLM 摘要能帮忙**：Kim、Muhn、Nikolaev（芝加哥大学，arXiv 2306.10224，工作论文）发现 ChatGPT 对 MD&A 和电话会的摘要短得多，却**比原文更能解释股价反应**；原文的「臃肿程度」还和更低的定价效率相关 ⚠️ 早期版本用 GPT-3.5、样本小 → 支持「一句话解释」用 LLM 写，但数字必须锁在原文上
4. **财报后漂移（PEAD）有争议**：Martineau（2022，*Critical Finance Review*）认为非微型股的漂移在 2006 年前后就消失了，市场在公告当天就把消息定价完；2025 年又有两篇论文反驳 ⚠️ → **卡片里不说「财报好，股价接下来还会涨」**。（更正：前面回答 Yu 时引了 Bernard & Thomas 1989，却没说这个结论现在有争议，那样讲不全面。）
5. **散户在财报前扎堆、财报后离场，主要是注意力驱动**：Liang 等（2024，*Journal of Behavioral Finance*）、Michels（2025，*Review of Accounting Studies*）⚠️ 另有 Friedman & Zeng 认为散户交易能让价格更快反映财报 → 财报前的提醒只给信息（日期、上次说过什么、要看哪几个数），**不做倒计时、不制造紧张感**
6. **即时教育优于课程**（Fernandes 等 2014，*Management Science*；Kaiser & Menkhoff 有反驳）→ 术语（bookings、指引、DAU）在卡片里点一下就解释，不另开一页

## 三、设计

### 放在哪
- 股票详情页。**财报前 7 天到财报后 14 天**，卡片放在评级上方；其余时间收进「财报」tab
- 首页那一行事件提示：「DUOL 周二盘后发财报」（只提示一次）

### 三个阶段

**财报前（前 7 天）**
- 日期和时间（盘前 / 盘后，换成读者所在时区）
- **公司上次自己说的**：上一季给的本季指引（例：Q3 bookings $307M、收入 $302M）
- **这家公司市场最看哪几个数**：取上一封股东信重点讲的 KPI（DUOL = DAU 增速、bookings、毛利率）
- 不预测涨跌

**财报后（14 天内）**
1. **和公司自己上次说的比**：指引对实际（例：bookings 指引 $307M → 实际 $316.1M ✓ 超出）
2. **关键数的季度走势**：4–6 个季度的小折线（例：DAU 增速 21% → 23% → 29%）。**加速还是放缓**比单季数字更有信息量
3. **全年指引**：上调 / 维持 / 下调，旧→新（例：全年收入 $1,207M → $1,221M）
4. **市场反应**：第二天涨跌，并和大盘对比（接 US-227 归因卡）
5. **一句大白话**：意味着什么，为什么市场这样反应（LLM 生成）
6. 来源：文件名 + 日期 + 原文链接

**平时**：「财报」tab 留历次财报卡，变成一条时间线 —— 也能用来回看本站当时的评级对不对（接预测台账）

### 不做的
- 不做「超 / 未超分析师一致预期」（数据要付费，而且公司自己的指引就是更干净的基准）。以后如果有免费可靠的一致预期源再加
- 不做推送式「财报倒计时」
- 不在卡片里给买卖结论

## 四、数据与防编造（实现要点）
- **来源**：美股先做。SEC EDGAR 免费，GHA 美国 runner 能访问：财报日 → 8-K 附件 99（新闻稿 / 股东信）→ 10-Q 补全。财报日期用 yfinance 日历做备源。A 股以后用巨潮资讯网（cninfo，Fly 悉尼可以访问，见 US-131）
- **抽取**：LLM 把原文抽成结构化 JSON：`{metric, value, unit, period, yoy, guidance_old, guidance_new, source_quote}`
- **锁定校验（关键）**：每个数字都必须能在 `source_quote` 里逐字找到，`source_quote` 也必须能在原文里逐字找到；找不到就丢弃这条，不显示。一句大白话里出现的每个数字，必须在结构化表里存在，否则整句不显示（沿用 US-225「降级要说实话」的原则）
- **公司专属 KPI**：第一次由 LLM 从股东信提名，**人工确认一次**后存入 `stock_kpis`（例：DUOL → DAU、MAU、paid subscribers、bookings）。之后每季自动抽取同一组 KPI，保证口径前后一致
- **表**：`earnings_reports`（code, period, report_date, source_url, extracted_json, verified_at）
- **测试**：用 DUOL Q1–Q3 2026 三封股东信做黄金样本（数字已在 `research/duol_case_2026-11.md` 核对过），断言抽取结果逐项一致

## 来源
- Robinhood · Using earnings: https://www.robinhood.com/us/en/support/articles/using-earnings/
- moomoo · AI earnings analysis: https://www.moomoo.com/au/hans/learn/how-to-use-moomoo-ai-earnings-analysis
- moomoo · Earnings: https://www.moomoo.com/sg/hans/articles/earnings
- Fiscal.ai 用户评价: https://trustpilot.com/review/fiscal.ai
- YCharts segments & KPIs: https://ycharts.com/indicators/categories/segments_kpis
- Simply Wall St 财报短讯例: https://simplywall.st/stocks/us/software/nyse-snow/snowflake/news/snowflake-second-quarter-2026-earnings-beats-expectations
- Kim, Muhn, Nikolaev · Bloated Disclosures: https://arxiv.org/html/2306.10224v4
- Martineau 2022 · Rest in Peace PEAD: https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf
- UCLA Anderson Review · Is PEAD a thing again?: https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/
- Rees & Twedt 2010/2011 · Earnings guidance and beating forecasts: https://psc.ky.gov/pscecf/2012-00221/rateintervention@ag.ky.gov/10252012f/Rees_and_Twedt_-_Earnings_Guidance_and_Beating_Analysts_Forecasts_-_2010.pdf
- Michels 2025 · Review of Accounting Studies: https://link.springer.com/content/pdf/10.1007/s11142-024-09825-9.pdf
- Retail trading around earnings (Robinhood): https://bohrium.dp.tech/paper/arxiv/619b86161c45e57ce929a7d7
- Friedman & Zeng · Retail trading and market reactions to earnings: https://scholarspace.manoa.hawaii.edu/items/ac246f3a-13bf-43f8-b5c0-55a302f690e9
