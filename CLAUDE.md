# 私人巴菲特 · Claude Code 工作手册

> 每次新会话开始前读这个文件。不确定做什么就回来看。

---

## 双语规范（强制）

这是中英双语网站。协作者 Da-young 不懂中文。

**所有模板里的用户可见文字必须走 `t['key']`，禁止硬编码任何语言的文字。**
新增 UI 文字时，同步在 `i18n/zh.json` 和 `i18n/en.json` 里加 key。

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
  - ML Phase 1 特征字段从未填充：`_run_layer2` 的 `save_analysis` 调用补填 `feat_sentiment_avg` / `feat_fund_flow_net` / `feat_pe_vs_hist` / `feat_price_momentum`（5日均涨跌幅，stock_prices 计算）/ `feat_fear_greed`（CNN Fear & Greed，macro 快照读取）
  - CLAUDE.md 市场覆盖表补入澳股（AU）和韩股（KR）
- **US-66 机构意向综合评分（2026-05-01）**：`compute_intention_score()` 加权评分（7信号×权重，tanh归一化）；`_PHASE_TABLE` 五阶段（聪明钱在大量买入/有机构在悄悄建仓/机构暂无明显动向/机构在陆续减持/聪明钱在加速离场）；`format_institutional_section()` 新增意向总览表 + 每股评分+依据行；`run_institutional_radar()` 接入评分计算
- **US-67 机构前兆信号（2026-05-01）**：`scripts/precursor_signals.py` 新模块；三类前兆信号（机构调研热度`stock_jgdy_tj_em`/融券余量变化`stock_margin_detail_sse/szse`/机构参与度趋势`stock_comment_detail_zlkp_jgcyd_em`）；接入 `compute_intention_score()` 新增3个权重项（survey 1.5/short_selling 1.0/participation 0.7）；所有10个信号描述全部改为人话（用"公司高管用自己的钱买了"而非"高管增持"）；五一假期API返回null的回退处理
- **US-68 机构雷达叙事重设计（2026-05-03）**：`_classify_inst_sellers()` 区分ETF被动调仓 vs 主动基金；`_build_observations()` 生成"综合来看"观察列表；`_SIGNAL_CONTEXT` 每个信号附"这是什么"人话解释；前兆信号移至页面顶端；`_renderIntention()` 完全重写为叙事结构；`signals_snapshot` 含 inst_top/margin/fund_flow；语言原则：只陈述观察、解释情境，不替用户下结论
- **US-76 最值得关注榜单（2026-05-06）**：`radar_app/data/signal_events.py` 新模块；11类信号（调研/参与度/融券/主力资金/机构增减持/融资余额）事件检测 + 共振算法（≥2同向信号触发上榜）；`/api/signals/watchlist` GET 端点（读本地缓存，<0.1s）；首页今日信号区块（`has_cn_stocks` 控制显隐，有A股才展示）；上榜卡片（看多/看空方向色条 + 信号tag + 共振进度条）；空态"接近触发"预览（4类信号进度条 + 触发条件提示）；点击跳转 `/stock/{code}?tab=radar`；实测60只A股扫描，8只上榜，5只接近触发
- **US-76 数据质量修复（2026-05-08）**：主力资金改用 ratio≥3% 相对阈值（原 net>0 对小盘误判）；机构持仓要求≥2家同向才触发（原≥1）；融资余额信号加48h新鲜度门控（`signals_age_h`）；`survey_events` 永久积累表（`core.py` 新建表，`save_precursor_cache` 写入，`_parse_precursor_cache` 回填兜底，历史191条事件backfill完成）；接近触发区增加方向感知（看多/看空预警色标签 + 卡片左侧色条）
- **US-92 详情页全面重设计（2026-05-18）**：
  - 4个纯规则函数（`describe_margin_context` / `describe_survey_context` / `describe_participation_context` / `label_news_vs_institution`）在 `scripts/buffett_signals.py`，32个测试全通过
  - `precursor_history` 表（每日快照 INSERT OR IGNORE + 90天滚动清理）；`signal_predictions` 新增 `signal_type` / `predicted_outcome` 字段
  - `save_precursor_cache()` 同步写入 `precursor_history`
  - `/api/predict/<code>` POST 新增 `signal_type` / `predicted_outcome` 字段
  - 5个 tab URL → 单页 `/stock/<code>`（旧 URL 301 重定向到 `#section` 锚点）
  - `stock/detail.html`：sticky 锚点导航 + IntersectionObserver 高亮 + sessionStorage 滚动恢复
  - §2 市场信号：背离摘要卡（新闻×机构9态矩阵）、信号叉乘情境卡（融券/调研/参与度，A股专属）、每条新闻一致性标签（一致/背离/逆向）
  - 机构雷达懒加载（IntersectionObserver，进入视口才触发）
  - `backfill_returns.py` 扩展：同时回填 `actual_return_10d`
- **D评级修复（2026-05-25）**：THS海外封锁→所有A股 annual_json=[] 缓存锁死→全部D；修复：`_fetch_cn_financials_em()` 东方财富备源；`pipeline_jobs.py` 空 annual_json 视为永远过期；生产数据批量回填
- **US-93 持仓透视卡（2026-05-25）**：`_build_position_insight()` in presenter.py；`get_price_52week` + `get_watchlist_entry` in data/stocks.py；detail.html §1 卡片（买入价/浮盈亏/持有天数/年化收益率/52周区间进度条）；stock.css `.pos-insight-*` 样式
- **US-94 分析师共识卡（2026-05-25）**：`analyst_consensus` 表；`scripts/fetch_analyst_consensus.py`（stock_profit_forecast_ths，机构数+EPS预测）；`/api/analyst/<code>` 端点；detail.html §2 卡片；48h pipeline 缓存；bug fix: `db.get/save_analyst_consensus` 不存在→改用 `radar_app.data.stocks` 直接导入
- **US-95 行业信号卡（2026-05-25）**：`industry_signals` 表；`scripts/industry_signals.py`（stock_board_industry_hist_em 30日涨跌，cycle_commodity 额外拉 macro_china_pmi_yearly 连续扩张月数）；pipeline 1b 层集成；detail.html §2 顺风/逆风/中性卡片；24h 缓存；graceful fallback
- **US-97 自动供应链溯源（2026-05-30）**：`scripts/supply_chain_mapper.py`（SEC EDGAR CIK查找 → 最新10-K URL → Risk Factors 提取 → Groq LLM结构化提取 → chokepoint_score 0-100打分 → yfinance ticker查找 → 写入DB）；`supply_chain_links` 表（downstream_code/supplier_name/supplier_ticker/dependency_type/chokepoint_score/evidence_quote）；`/api/supply-chain/scan/<code>` POST（后台线程触发）；`/api/supply-chain/<code>` GET（读缓存）；detail.html fundamentals区新增「上游供应链」section（仅美股显示，扫描按钮+轮询+供应商卡片含风险进度条+证据引用+"加入自选股"按钮）；stock.css `.sc-*` 样式；30天缓存TTL
- **US-96 Serenity 供应链瓶颈框架集成（2026-05-30）**：`scripts/serenity_theses.py` 静态论文库（SIVE/AXTI/MU/NBIS/LITE/COHR/AAOI/LPTH 8只股票，conviction/supply_chain_role/thesis/催化剂/失效条件/ATM风险）；`SYSTEM_SUPPLY_CHAIN` + `SYSTEM_SUPPLY_CHAIN_EN` prompt 注入 `buffett_prompts.py`；`FRAMEWORK_MAP` 新增 supply_chain 路由；`buffett_context.build_serenity_context()` 格式化上下文；`classifier.py` 新增 supply_chain company_type 检测（非A股 + 代码在论文库 or sector 关键词）；`analyze_stock_v3` 新增 `serenity_context` 参数，注入 user_msg；pipeline 自动 log "注入 Serenity 供应链论文"
- **US-79~91 美股信号引擎（补录，2026-07-12 审计确认已实现）**：`pipeline_fetch.py` `_fetch_us_institutional`/`_fetch_us_insiders`/`_fetch_13d_activist`（13F机构/Form4内部人/SEC EDGAR 13D维权）；`radar_app/data/signal_events.py`（共振算法+独立性检验）；`scripts/buffett_signals.py` 情境函数。US-88/89/90/91 信号研判引擎主体在此
- **US-98 i18n 三大模板双语化（补录，2026-07-12 审计确认）**：detail.html 等用 `{{ t.xxx }}` 点号写法（detail.html 235 处），双语已落地
- **US-118 每股重大动向解读（补录，2026-07-12 审计确认）**：`scripts/news_interpret.py` 重大新闻自动过滤 + 人话解读，接进 stock_pipeline / stock_report
- **US 状态审计纠错（补录，2026-07-12）**：一次「没做的 US」审计误把已实现项记成未做，实地核验纠正 —— US-69（`precursor_scan.py` + `scan-svc.yml`）✅已实现；US-71（`fund_rater.py` 四类基金评分 + `fund_fetch.py`）⚠️大部分实现；US-99（`openapi.yaml` 30端点 + `flask-cors` + `shared/response.py` `{ok,data}` 信封 + `audit_routes.py`，`app.py` 已是 6 行 shim 拆 11 blueprint）✅基本完成，仅剩 SPA 去模板化；US-101（`run_multihop_scan` + `get_supply_chain_tree` + `hop_depth` 三列，接进路由）✅已实现。真未做的只剩 US-07/15/16/17、US-72（geoIP locale）、US-70 自动优先(部分)、US-75 预言家日报完整 epic(部分)。**根因=状态只活在散文里靠 grep 重猜→已在 PRODUCT.md 每个相关 US 头部加权威「实现状态」行（SSOT），以后审计直接读不再猜**
- **Bug fix: `stock_precursor_cache` 无界增长（2026-07-12）**：该表本是"最新"缓存（所有读方都 `ORDER BY fetched_at DESC LIMIT 1` / `MAX`），却只 INSERT 不清理→每次扫描每只堆一行，最差 91 行/只、4894 行/4 MB、冗余于 `precursor_history`。修：`market.py` 写入后 `DELETE ... WHERE code=:code AND fetched_at < :keep` 只留最新一行。生产已 prune 4894→114 + `VACUUM FULL`（3960 kB→216 kB）。⚠️ 代码修复需部署后对新写入才生效
- **US-123 日报改造：删数字堆砌、只推有用信号（2026-07-12，待部署）**：诊断——每天推的「股票日报」(Bear+Server酱)是空壳:旧 monolith `stock_pipeline.main()`(cron.yml 08:00 UTC，真正的每日推送源；push-svc 只手动没排班)自己在美国 runner 抓 A 股→抓不到(US-122 地理问题)→评级/行情/个股动态全空表头，且 `reports` 表停在 07-10 重复推。而 fetch-svc/svc_analyze 明明把新鲜行情(183只)+评级(42只 quant_score)存进 DB，`generate_report` 不读 DB 坚持自抓。用户定:数字堆砌不要，删。改:① monolith + svc_push 都删 admin 数字堆砌推送(Bear/Discord/空壳 serverchan)，只保留 `save_report`(网站 /report 归档不动)。② 增强 `build_user_push_content`(stock_report.py)——在早期预警+评级变化基础上加 `_signal_leads_for`(get_signal_conclusion lead/high)、`_prophet_dirs_for`(复用 US-75 `_build_prophet_series` 升/降)、`_catalysts_for`(get_upcoming_events_for_user 7天)，五块全空不推。③ `admin_user_id()`(role='admin' 最小 id) → 有用 digest 发 SERVERCHAN_KEY，只走 Server酱。全读 Neon DB→GHA 美国 runner 可跑不碰东财。实测 admin 23 只自选:今天有 机构领先信号2(002444⚡)+预言线升6降6+评级变化1，非空。门禁+组装 monkeypatch 测过。**待部署(cron.yml 是真推送源)**
- **US-124 /report 归档也改用有用日报（2026-07-13，待部署）**：US-123 删了推送但网站 `/report` 仍渲染 `reports` 表的数字堆砌 md。核实：日 md 唯一真消费者是 `/report`（`dashboard/query.py` 的 `latest_report` 等键无模板引用）；数字堆砌 `generate_report` 只被 `stock_pipeline.py:241` 一处调。改：monolith 存进 reports 表的日 md 改成 admin 的 `build_user_push_content`（去掉"详情见网页"尾行，空态存占位），一份 digest 既 save_report 又 send_serverchan（一次算两处用）；物理删除 `stock_report.generate_report`（362 行 + 清 config 4 常量 import）。/report 模板不改（只 `marked.parse(report.md)`，存什么渲染什么），周/月/季 digest（periodic_digest 自己的 generate_report）+ accuracy 页不动。**已部署**（07-13 手动 save_report 让 /report 立即显示今日 digest）。顺手清死代码：删 `_get_buy_watching`/`_stock_price_str`/`_score_report`/`_stock_card`/`PUSH_QUALITY_THRESHOLD`（全仓 0 调用）+ 失效 import（datetime/timedelta/CN_TZ/4 个 config 常量），stock_report.py 448→162 行，零行为变化，搭下次部署上
- **港股搜索修复 · 数据驱动零硬编码（2026-07-13，已部署）**：mom 追热点搜港股(泡泡玛特/阅文等)"没一个对的"。根因两处：① `radar_app/search/service.py` 把**纯数字**当中文强制转 A股(`query.isdigit()`),港股代码永远被劫持→改成只有**中文字符**才转；② `_search_intl_only` 数字代码没转 `.HK`。**先搜 prior art(用户要求)**：东财/sina 港股名单在 US 和 Fly 悉尼都被墙→找到 **HKEX 官方 ListOfSecurities**(香港服务器，Fly 可达，含中英文名)。生成 `data/hk_stocks.json`(2818 只港股 code→简体名，HKEX 中文 xlsx + opencc t2s，一次性本地生成)；`stock_search._load_hk()`+`_search_hk_list()` 离线加载搜索(中文名子串/代码前缀→`XXXX.HK`)；`_search_intl_only` 优先查官方名单再 yfinance 兜底(US代码)。**关键坑：`.dockerignore` 有 `data` 排除整个目录**(cn_stocks.json 靠运行时 akshare 现抓，港股抓不到必须打进镜像)→加 `!data/hk_stocks.json` 负向放行。曾误加 4 个硬编码名字被用户抓到→已删，改数据驱动。名单会随新 IPO 变旧，重生成=Fly 拉 HKEX 中文 xlsx + t2s
- **EPIC-A 短线生命周期 · 进行中（2026-07-14）**：两轴——🧬进化(长期公司变强/变弱,ROE趋势+护城河方向+评分) × 🎂年龄(短线五阶段:胚胎/幼年/壮年/老年/迟暮,领先信号+动能+估值)。比喻是串联法，每阶段挂真信号。框架见记忆 [[project_signal_inventory]]。PRODUCT.md 有 EPIC-A + US-129~137(一个数据源一个US)。
  - **US-129 阶段引擎 + 摇钱树页面（已部署，2026-07-16）**：`radar_app/stocks/lifecycle.py` `build_lifecycle(code)`——两轴、规则透明、每判断挂真信号。生产实测:比亚迪=幼年+变强、中芯=老年(PE98%透支)、赣锋/华闻=迟暮，准。**页面 `/stock/<code>/lifecycle` 已做**：国风青绿×数据(桃源深处/千里江山图美术方向)——Canvas 生成摇钱树,**树冠茂密/翠绿=树势(长期进化,evo direction 驱动 depth+叶色)、枝头暖金元宝=短线阶段(stage→元宝数:抽芽0/初结3/满树11/摇树9+掉落/落叶1)、根部养分芯片=stage.evidence(点开跳 signals 页看真数据)**;金线标注树势/元宝,5段轨(抽芽·初结·满树·摇树·落叶),一句 verdict + 两轴拆解卡。样式内联 `.mt-` 前缀主题感知,`@admin_required` 内测。隐喻链:养分(信号)→喂树→旺→结元宝;"元宝越满≠越该买"(刚结=机构建仓=买,众人摇树=散户接盘=卖)。设计决策见记忆 [[project_signal_inventory]]。
  - **US-131 招投标/中标信号·🥚胚胎期（数据链已通，待排班）**：`scripts/tender_signals.py`。**关键:东财公告流被墙(现有 catalyst_calendar 名存实亡,11条停0710)→找到巨潮资讯网 cninfo 为可达官方源**(Fly能连,POST `hisAnnouncement/query`,搜"中标"18345条,含重试防DNS抽风)。`run_tender_refresh(codes)` 存 stock_events(source='cninfo_tender',只存stocks表内已跟踪股,FK约束)。引擎 `_recent_tender` 读到→亮🥚胚胎期。端到端验证:华康洁净(301235)→胚胎期+"近期中标"依据。**中标只对项目型公司(工程/IT/环保)有意义,消费/制造股不亮(正确)**。待办:每日 tender 刷新排班 + 页面。
  - **US-134 搜索热度→验证更正为老年/接盘信号**(非胚胎;Da-Engelberg-Gao:注意力飙升=2周后反转=晚期)。
- **US-128 统一「添加股票」搜索组件（2026-07-13，已部署）**：所有添加入口统一同一套 UI，避免困惑。可复用组件 `templates/stock/_add_search.html`（提示语「今天想成为哪家公司的股东？」+ A股/基金/海外 tab + 🔍 大搜索框 + 下拉 + 选中即静默 `/api/watchlist/add` 加入自选 + command 面板；设计语言来自 landing，**隐藏了"研究/算值多少"命令**=纯添加）。首页 index.html 与 watchlist.html 均 `{% include %}` 替换旧的"光秃秃添加按钮+折叠面板"。`.add-search/.as-*` CSS 主题感知（static/style.css）。旧 add JS 留为死代码（`SearchWidget.bind` 有 null 防护、其余仅被已删按钮调用），`toggleAddPanel` 重指向聚焦 as-search，`_isSearching` 改看 as-search+wl-search。生产两页渲染 200 验证。注：US-114 价值发现 4 步页仍是死代码（`register_value_routes` 未调用），本次只借其搜索 UI 设计语言，研究功能不上线（见记忆 [[project_us114_state]] 战略定位：US-114 重点深做但不急上线）
- **US-126 首页重构（2026-07-13，已部署）**：极简化——近期事件从大黄框改成 masthead 一行提示（`home-event-line`，无事件不渲染）；删"我的选股"卡片（顶栏已有入口）；「添加」提到正文第一；今日信号(US-76)/市场新闻/知识专栏(DS-06) 全部折叠或隐藏（`<details>` + `{% if show_knowledge_column %}` 暂藏）。新首页顺序：事件行→添加→行业专栏预览→今日信号(折叠)→新闻(折叠)。CSS 在 static/style.css
- **US-127 行业分析专栏·精选库（2026-07-13，已部署）**：`radar_app/research/`（articles.py registry + routes.py：`/research` 归档 + `/research/<slug>` 全文，`?embed=1` 隐藏返回按钮供预览）；`templates/research/<slug>.html` 自包含文章文件（Claude 手作 artifact 落地）；首页「添加」后一张**预览**（iframe 嵌真文章显示一半 + 底部渐隐遮罩 + "阅读全文"按钮，`research-preview/rp-*` CSS）；`build_dashboard_context` 注入 `featured_research`。**第 1 篇=奶茶六强(milk-tea-2026)**。**铁律：精选库、人工深研、不套模板不自动生成**（见记忆 feedback_research_column_ethos）。新增一篇=加 registry 条目 + 放模板文件
- **US-125 自选股排序（2026-07-13，已部署）**：最新添加在前(`added_at DESC`)；差评(D/D-)沉底(presenter `is_poor` + service 稳定排序)；分析完成为差评时卡片播 `.wl-sink` 掉落动画再落位(尊重 reduced-motion)；修 US-120 擂台手机端不可达 bug(`setView` <480px 把 list 退回 card 导致 arena 失联→改宽度感知循环 `['card','arena']`)
- **US-124 /report 归档改用有用日报（2026-07-13，已部署）**：见下 US-123，同批把 /report 的数字堆砌 md 也换成有用 digest，删 `generate_report`
- **US-75 预言家线 v1（2026-07-12，待部署）**：方法论根=Smart Money Flow Index（机构脚印累积成线、天生领先、背离时最强），不照抄 SMFI 日内算法（A股无可靠日内）。数据脊梁已在（`precursor_history`，生产 42 交易日、核心 30+ 只覆盖 30–37 天，不可 backfill 只能自然长）。`prophet_daily_score(participation, survey_inst_today)`（buffett_signals.py，纯规则）：**只有当日真观测进累积**——参与度 z 分（当日 vs 30 日均值）+ 当天新增调研加成；融券是滚动值不按日归因故不进累积。`_build_prophet_series`（presenter.py）：调研事件在"首次出现在快照的那天"标注（seen 去重、首日只播种），修了初版"同一调研每天重复标注+双重计数"的 bug。`get_precursor_history`（market.py）。signals.html §2 顶部：原生 SVG polyline + JS 十字光标（复用 US-119 写法，不引库）+ 注释点 `<title>` + 方向色（升绿/降红）。`.prophet-*` CSS 主题感知，7 双语 key，7 单元测试（共 39 全过）。生产 5 只长历史股实测算法通过（注释多样、无重复）。**待部署才看得到活图**（生产跑 v247、本地无 A 股数据）
- **US-119 机构动向榜单重设计（2026-07-12 完成）**：① 数据层(signal_events.py `_calc_resonance`/`smart_money_vs_price`/`conclusion_text`,纯规则三态:共振/领先背离/分歧)早已做 ② 首页榜单(sr-conclusion 一句结论+⚡领先+高置信,删误导的"背离N"chip `_divergenceChip`死代码)已做 ③ 详情信号页 `signals.html` §2 四层重排:`get_signal_conclusion(code)` 复用同源模型→presenter 注入 `signal_conclusion`(仅A股)→层1 sig-verdict 横幅(与首页逐字一致 AC6)；层2 调研/参与度情境卡突出+"研究→参与→资金→价格"领先指标框架；层3 三列信号地图+行业折进`<details>`；背离摘要+综合研判折进`<details>`(渐进披露)。**关键发现:`stock/detail.html`(US-92单页化产物)从没接进路由=死代码,真页面是多tab的 letter.html/signals.html/radar.html 等**。sig-verdict/sig-fold/sigctx-lead-hint CSS + 6个双语i18n key
- **US-119 信号可视化 + 数据修复（2026-07-12 续）**：机构调研=交互式月度柱状图（`_build_survey_chart` 近6月家数聚合，hover 看家数/次数/方式，空月留基线细痕）；机构参与度=日频折线图（`fetch_inst_participation_trend` 加 `series` 日频序列，SVG polyline+均值虚线+JS十字光标 mousemove 值跟随）。修 2 个真 bug：①参与度不是空数据是 presenter 读错字段名（`latest_pct`→`latest`，其他地方一直读对，仅详情页错）②radar-svc "0只A股"空跑（`_cn_codes` 用 `get_active_watchlist_stocks` 仅推送用户→改 `get_all_cn_watchlist_stocks`）。**基建**：新建 `scan-svc.yml`（`gh workflow run` 一键触发 precursor 扫描，curl `/api/trigger-scan` async；东财必须 Fly悉尼跑不能GHA美国runner；ssh -C 长任务会断、push自动部署会杀运行中scan——都踩过）。自动刷新：cron.yml `light` 任务每工作日16:00CST独立跑（不被monolith拖累）。实测生产 109/111 A股 participation series 已populate
- **US-120 股票擂台赛（2026-07-12）**：`get_leaderboard(user_id, baseline_days=7)`（radar_app/data/analysis.py）按最新 quant_score 降序排名 + score_change(vs上次分析) + rank_change(vs baseline_days前排名，NEW=新上榜/—=无变化)，staleness 无关；无分股票 NR 排最后不占名次；已卖出不计入。`/api/leaderboard` 端点（watchlist/routes.py）。watchlist.html「擂台」视图=toggleView 第三态（卡片→列表→擂台循环），奖牌🥇🥈🥉+分数+升降箭头，懒加载 fetch；static/css/watchlist.css `.arena-*` 样式（主题感知，前三金/银/铜边）；i18n/watchlist.json 加 7 个双语 key。注：底层 grade 与 quant_score 偶有不一致（grade 来自LLM，分来自定量），擂台严格按分排
- **US-122 fetch-svc throughput（2026-07-10，B方案不花钱纯技术，三轮云端验证通过）**：根因=数据在中国/runner在美国，东财海外限流~60s/只，131只跑不完。① `fetch_priority_codes()`（stocks.py）持仓→观察→已卖出，同级按 stock_prices.fetched_at staleness 升序（`NULLS FIRST` PG兼容），staleness本身即游标；svc_fetch 用它取代 all_watched_codes。② US-121 `force=False` 缓存真生效（原 force=True 每轮全量重抓）。③ `fetch_with_fallback()`（stock_fetch.py，akshare-one同款+per_timeout快速失败）；主力资金 `[东财→新浪 MoneyFlow]` fallback（东财海外全挂→新浪救，0%→96%）；新闻东财唯一源退避重试。④ `fetch_cn_signals` 三东财调用（质押/融资/机构持仓）套 `_call_with_timeout` 8s快速失败 + 融资明细按(市场,日期)跨股缓存 + 失败也缓存None（cn每只30s→4s）。⑤ gap 仅A股且真跑层才睡。**效果：一轮覆盖 50→124/134，1c2超时 31→1，整 watchlist ~1.3轮刷完。追踪见 US121_ROLLOUT.md。待办：US-121第3步给 fetch-svc 加 schedule。**

- **US-138 monolith 退役 · US-121 收尾（2026-07-29，已部署）**：**事故**——`stock_pipeline.main()` 从 07-15 起连崩 10 个交易日：`institutional_radar.py` 回购进度 `pct_done` 为 NaN → `int(NaN)` 抛 ValueError，崩点(line 239)之后的日报/`/report` 归档/Server酱 推送/新闻入库全部陪葬；`Alert on failure` 依赖的 `SERVERCHAN_ADMIN_KEY` 从未配置 → 全程静默 10 天。**根因链**：US-121 拆分只走到「切了 fetch-svc」就搁置 17 天，monolith 仍当家 → 拆分的失败隔离价值为零。**修**：① `_safe_float` 兜 NaN/Inf（`float(nan)` 不抛异常是坑，同 bug 在龙虎榜 `int()` 处也埋着）+ 10 单测；② **6 件孤儿步骤**（拆分时无人接手，直接关 monolith 会静默消失）归位——新建 **market-svc**（宏观快照**改为落库**/国际新闻/重大新闻扫描，即 US-121 表里「待接」的 material-svc 并入）、催化剂→radar-svc、持仓 Layer2→analyze-svc、`/report` 归档→push-svc（与推送同一份 digest）；rbnz/nzx 三个**不搬**（US-124 删 `generate_report` 后零消费者，每天白抓）；③ 排班错峰 fetch 07:00→analyze 08:00→radar 09:00→scan 09:30→market 09:40→digest 10:20→push 10:30（UTC 工作日）；④ monolith `if: workflow_dispatch` 只留手动回滚入口，`light` job 删 trigger-digest 保留 trigger-scan（**东财只能 Fly 悉尼跑**）；⑤ 6 个 workflow 告警加 `SERVERCHAN_ADMIN_KEY || SERVERCHAN_KEY` 回退。**顺带查清**：生产 `user_push_settings` 只有 user 2 一行且 `notify_daily=0`、无 key —— **per-user 推送在生产一直是空的**，真正发出去的只有全局 `SERVERCHAN_KEY` 那份 admin digest（本地 sqlite 里 mom 有 key 是开发数据，别照它推断生产）

- **US-139 排班首日三处失血（2026-07-30，已部署）**：US-138 排班第一天全链路跑起来后暴露，**手动单跑全测不出来**——① **analyze-svc 一封信都没生成**（US-138 引入的回归）：量化刷新放 LLM 循环前且无预算，211 只×14.5s 吃光 50 分钟 → `items_processed=0` 却 `status=done`；修：跳过当天已算过的（`save_analysis` 本就 `ON CONFLICT(code,period,date)`）+ **一条查询拿「今天已算」集合**（per-stock 查才是 14.5s/只的根源——GHA↔Neon 每趟往返都要钱，`_run_layer2` 每只发 ~10 次独立 `get_conn()` 还带 `pool_pre_ping`）+ `QUANT_BUDGET_MIN`(20) 独立预算 + LLM 预算在其后才起算；② **radar/market 撞 45min timeout 被 SIGKILL**：三个东财消费者时间窗重叠（radar/market/Fly scan）互相拖慢；修：`fetch_precursor_signals(deadline=)` + `run_institutional_radar(budget_min=)` + `RADAR_BUDGET_MIN`(70)、`MATERIAL_MAX_MIN` 25→20、timeout radar 90/market 60、**东财消费者串行化**（radar 11:00→scan 12:45→market 13:00→digest 14:15，push 仍 10:30 不动=用户可感知锚点，radar/market 结果进次日 digest 符合 US-121「读 DB 最新可用」）；③ **被 kill 的 run 永远停在 `running`**（SIGKILL → `finally` 跑不到，记账里长得像还在跑，反而掩盖掉链子的服务）；修：`service_run()` 启动时收尸同名服务 >3h 的 `running` → `killed`，3 个测试（陈旧标 killed/新鲜不误杀/异名不牵连）。**教训：排班的失败模式（并发、争抢、预算耗尽）手动单跑一个都测不出来，只能上线后看首日。**

- **US-140 快照冻结 14 天 · 批量取价 + Groq 预算硬闸门（2026-08-11，已部署）**：US-138/139 后 5 服务连日全绿，**但网站快照从 07-29 冻结 14 天**，Routine 天天读陈旧数据、连写 14 天 skip 日志、连推 8 天告警。**Routine 的根因诊断是错的**——它认定是 `daily_digest.py` 熔断，连 5 次请求手动跑 digest-svc；那个熔断（当日新价格覆盖率 <50% 就中止 commit）是 2026-07-01 伪快照事故的守门人，**按设计正确工作**，手动重跑一百次也是同一结果。真根因在上游一层：自选股涨到 208 只 → fetch-svc 逐只抓(每只~30s) → 40 分钟预算只覆盖 81 只 = 38% → 熔断。修：**价格是唯一「全量覆盖才有意义」的数据**（熔断/快照按覆盖率判断）→ 单独拎出 `_bulk_prices()` 走批量，跑在逐只深度层之前（预算在其之后才起算，US-139 同款教训）；深度层仍按预算轮转不变。**两段式**：A股一次新浪批量(`fetch_quotes(fallback=False)`)→立刻写库→新浪缺的连同海外股一起走一次 `yf.download`（yahoo 认 `600519.SS`）。**首轮云端实测踩坑**：新浪批量在 GHA 整批失败（`stock_fetch` 里那条注释早警告过），`fetch_quotes` 掉进逐只 178 次 yfinance 内部兜底、25 分钟只打印一行就没动静，且写库在函数返回后才做=全有全无 → 才加 `fallback` 参数。生产实测覆盖率 78→150/215(70%)，过阈值。附带修 **market-svc 3/4 次被 SIGKILL**：material scan 名义预算 20 分钟实跑 60 分钟——预算只在「每只之间」检查，单只内部撞 429 会 `sleep(452s)`(Retry-After)，每只睡 7.5 分钟闸门形同虚设 → `buffett_groq.set_call_deadline(ts)`，429 要睡过 deadline 就返回空串让调用方降级；接进 material scan + analyze-svc（后者 08-10 那轮也超预算 20 分钟，只是没撞破 90min timeout）；未设 deadline 的调用方（网页端即时请求）行为不变；4 测试。**教训：熔断/保护机制报警时，往它的输入端上游找根因，别去重跑熔断本身；另一个 agent 的根因结论必须独立核实（这次它把守门人当病因）。**

- **EPIC-B 老股民视角领先信号（2026-08-11 起，来源：股民小刚）**：7 条建议逐条评估后立项 US-141~147（PRODUCT.md）。**贯穿三条纪律**：不给仓位建议（那是投顾）／只陈述观察不替用户下结论（US-68）／能回填就必须回填且打分难看照实说。评估要点：小刚「跌久了就便宜」方向对但**「跌了多久」本身是负信号**（中期动量为正，只有 3–5 年才反转）；「超大单=主力」**东财是按单笔金额猜的不是真身份**（机构可拆单、大户可一笔）；「吸筹/洗盘/出货」**是事后叙事、不可证伪**（涨了叫吸筹跌了叫出货）→ 必须下死定义+回填打分；「被量化控制」**不可检验**（量化占成交两成多，答案永远是「有」）→ 改名「现在这票是谁在定价」。
  - **US-141 便宜但没坏（已部署）**：`describe_cheapness()`（buffett_signals.py，纯规则）估值分位 × 进化轴 → 六态（错杀/价值陷阱/便宜但横着/好贵/双杀/中性 + 数据不足不硬猜）；复用 `lifecycle._evolution` 不做两份；低估值三态必带挡刀句「从高点跌了多少，不代表还能跌多少」；letter.html 接在评级后（结论先行）+ 依据折进 `<details>`；15 测试含**措辞纪律测试**（禁「安全边际/仓位/抄底」）+ 双语。生产交叉验证与 lifecycle 独立判断一致（茅台 PE17 分位+变强→错杀；中芯→好公司但不便宜，lifecycle 也判老年 PE98% 透支）。**注：`stock/detail.html` 仍是死代码，真页面是 letter/signals/lifecycle 等**
  - **US-142 谁在卖自己公司的股票（已部署）**：**原源已死** —— `ak.stock_share_hold_change_sse/szse` 从 NZ 和 Fly 悉尼都 ConnectionReset，生产 `insider_changes` 四个月只 11 行。搜了三个候选：cninfo 公告(能查到「减持」377条但**只有标题拿不到比例**)、`webapi.cninfo.com.cn`(Fly 上**DNS 都解析不了**，与可用的 `www.cninfo.com.cn` 不同机)、**东财 datacenter `RPT_EXECUTIVE_HOLD_DETAILS`（Fly 可达、字段全结构化）** ← 采用。`CHANGE_RATIO`=占总股本、`END_HOLD_NUM`可算占本人持股、`CHANGE_REASON`判惯例性。**⚠️ 东财只能 Fly 悉尼跑**。`classify_insider_move()` 依 Cohen-Malloy-Pomorski(2012)**只有机会性交易有信息量**分惯例/机会性（大额即使原因机械也算机会性）；**卖出的「占本人持股」分母必须用卖前持股**（卖后+卖掉的），否则卖光的人永远显示 100%；窗口 30→180 天；必带 caveat「高管卖股票理由可能很私人，一笔不说明问题」；20 测试
  - **US-148 规则叙事 zh-only 欠债（待做）**：双语规范守住了模板层，但 `describe_*`/`conclusion_text`/`_SIGNAL_CONTEXT`/`lifecycle._evolution` evidence 等**规则生成的正文全是中文、绕过 t[]** → Da-young 切英文只有外壳是英文。US-141 已按正确姿势做（`locale=` 参数 + 双语串表 + 「en 输出无中文」正则单测），可作模板

### ❌ UI 待做（暂停）
- US-07 组合分析 /portfolio（无路由，较大功能）
- US-15 新闻情境化（标注影响哪只持仓）
- US-16 Watchlist 缩略图模式
- US-17 巴菲特++雷达图

### 🔄 下一阶段（按优先级）

**⚠️ 部分完成 / 有残留 bug（2026-04-16 已修复项见下方）：**
- **US-55 数据三层分离**：`/api/refresh-news/<code>` POST 端点存在且有1小时缓存 ✅；`/api/news/<code>` GET 端点已修正为返回7天数据 ✅（原为3天）；stock.html 「更新新闻」按钮已存在 ✅；「分析」与「更新新闻」已分离 ✅
- **US-56 港股/美股财务补强**：LLM prompt 禁 markdown 加粗 ✅（2026-05-19，buffett_prompts.py 所有 9 个 system prompt 加禁止规则）
- **US-59 推送质量门禁**：`_score_report()` + 阈值 40/100 ✅；所有持仓质量不达标时改发告知消息（不静默跳过）✅（2026-05-19）
- **US-60 买入区间+止损位 UI**：===TRADE=== 解析已实现 ✅；trade_block 已写入 DB（run_pipeline **结果**） ✅；`run_letter_only` 漏存 trade_block 已修复 ✅；stock.html 「操作参数」卡片已存在 ✅；app.py 路由未把 trade_block 单独传模板（analysis dict 里有，stock.html 直接读 `analysis.trade_block` 可正常工作） ✅
- **ML feat_* 字段从未填充**：`_run_layer2` 的 `save_analysis` 调用已补填 `feat_sentiment_avg` / `feat_fund_flow_net` / `feat_pe_vs_hist` / `feat_price_momentum`（5日均涨跌幅，stock_prices 计算）/ `feat_fear_greed`（CNN Fear & Greed，macro 快照读取）✅（2026-05-19）
- **US-38 业绩日历与催化剂追踪（2026-05-19）**：`scripts/catalyst_calendar.py`；`run_catalyst_refresh()` 每日从 AKShare 拉取限售解禁（`stock_restricted_release_detail_em`）和重大公告（`stock_notice_report`），存入 `stock_events`（source='auto_unlock'/'auto_notice'）；`get_upcoming_events_for_user(uid, days_ahead=7)` DB 函数；watchlist.html 顶部黄色催化剂横幅（7天内事件，今天/近期色标）；detail.html 事件 tab 新增 share_unlock/earnings_report/major_announcement/earnings_forecast 类型标签；pipeline `main()` 集成调用
- **Knowledge card popup 接入（2026-05-19）**：3个信号情境卡（融券/调研/参与度）接入 `/api/knowledge/<slug>`，`_kcard` 原始数值存 presenter.py，`data-params` + `JSON.parse` 模式避免 HTML 引号冲突，`.kcard-btn` + `.kcard-popup` CSS 新增

**数据层待补强：**
- 财务指标实时拉取：AKShare stock_financial_abstract_ths 拿 ROE/净利率/资产负债率（现在全是 NULL）
- 机构持仓变动：ak.stock_institute_hold / 大股东增减持公告
- 估值历史：PE/PB 历史百分位（现在只有即时值，没有历史对比）
- 北向资金：需收盘后运行 pipeline 才能验证 signals.north_flow 非 NULL（US-58 最后一项 AC）

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

## 部署流程（每次部署必读）

**⚠️ 生产部署 = 提交 + 推 main，不是 `flyctl deploy`。**（2026-07-16 血泪教训：本地改了不提交，`flyctl deploy` 跑了也白跑，页面"都没了"——因为真正的生产镜像由 GHA 从 main 构建，flyctl 临时镜像会被覆盖。）

**配置**：`fly.toml`（app=personal-buffett, region=syd, port=8080），入口 `run:app`（gunicorn）。

**标准部署（唯一可靠路径）**：
```bash
git add <改动文件>
git commit -m "..."          # 一个逻辑一个提交
git push origin main         # → 触发 .github/workflows/deploy.yml
```
`deploy.yml`（push main 触发）：`actions/checkout`（**只拿已提交的代码**）→ 构建镜像推 `ghcr.io/sodawaitress/personal-buffett:main` → `flyctl deploy` 到 Fly。约 3 分钟。**未提交/未跟踪的文件永远不会上生产。**

**推之前的体检**（合并大改动时）：
```bash
python3 -m py_compile <每个改动的.py>          # 语法
python3 -c "import run; print(len(list(run.app.url_map.iter_rules())))"   # 导入+路由注册
```

**远程 main 常被 cron 的自动 chore 提交推进**（daily snapshot / ingest predictions / routine log，只动 knowledge/output/snapshots 数据文件）。push 被拒时：`git fetch` → `git merge --no-edit origin/main`（零源码冲突，别用交互 rebase——本环境不支持）→ 再 push。

**盯部署**：`gh run watch <id> --exit-status`（`gh run list --workflow=deploy.yml`）。
**验证**：`curl -s -o /dev/null -w "%{http_code}" https://personal-buffett.fly.dev/healthz`（200 即好）。

**手动应急 flyctl deploy**（几乎不用；会被下次 GHA 覆盖）：先 `find . -name "._*" -not -path "*/.git/*" -delete`（外置磁盘 `._*` 会让 builder 报 xattr 错），再 `COPYFILE_DISABLE=1 flyctl deploy --remote-only`。

---

## 代码规范

- 改文件前必须先 Read，用 Edit 局部修改，**不用 Write 整体覆盖**
- 新功能写进 PRODUCT.md 对应 US 再实现，不擅自加功能
- 每个 User Story 确认后才实现
- 硬编码股票数据（BUFFETT_PROFILES、NZ_PROFILES）逐步迁移到 DB，不新增硬编码
- LLM 调用走 Groq API（`scripts/buffett_groq.py` 的 `_call_groq`，模型 `llama-3.3-70b-versatile`）。实测限速（2026-07-09）：**RPM 1000 / TPM 12,000**。瓶颈是 **TPM 不是 RPM**（一封信 ~2500–5000 tok，每分钟仅 ~3–4 封）。并发无用（TPM 账号级硬上限）；Batch API 免费档不可用（403 not_available_for_plan）。提速靠选择性分析 + token-bucket 配速，详见 US-121

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
