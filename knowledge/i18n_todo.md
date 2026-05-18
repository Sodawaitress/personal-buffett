# I18n TODO — remaining hardcoded Chinese strings

## CRITICAL — stored in DB, affect every analysis

### `scripts/pipeline_analysis.py`
- `_validate_signals()` lines 19–47 — data warnings ("PE数据缺失…", "PE为负…", etc.)
- `_analyze_earnings_quality()` lines 77–107 — earnings flag blocks ("【利润质量⚠️】…", "【ROE趋势⚠️】…")
- `_compute_trading_params()` lines 133–231 — trade parameter labels ("季线MA60附近，回调首选入场区", "年线MA250附近，强支撑区", position labels)

Strategy: pass `locale` down through `_run_layer2` (already done for rate_stock) → add `locale` param to these three functions → add `_T` dict.

---

## HIGH — visible in main UI

### `templates/stock/_head.html`
- Tab nav hints: "值不值买？", "市场在说什么？", "机构雷达", "聪明钱在动吗？", "基本面数据", "重大事件", "📋 导出分析包"

### `templates/stock/signals.html`
- Entire signals panel labels: "看多信号", "看空信号", "信号分歧", "独立来源共振"
- Column headers: "内部人视角", "最可信", "市场情绪", "中等可信", "结构背景", "背景参考"
- Signal labels: "北向资金", "沪"/"深", "主力资金", "融券方向", "机构持仓率", "内部人持仓", "新闻情绪", "情绪倾向"
- Fund type badges: "指数", "投行", "主动", "对冲", "其他"
- Divergence warning: "消息面偏正面，但机构行为背离", "查看机构雷达 →"

### `templates/stock/radar.html`
- Loading: "正在拉取机构信号，稍等片刻…", "（调研热度 + 融券余量 + 机构参与度，约需 15 秒）"
- Error: "加载失败，请刷新重试"

### `static/js/stock-radar.js` (~50 strings)
- `_SIGNAL_LABELS` dict: "高管增减持", "北向资金", "龙虎榜", etc.
- Signal weight labels: "高权重", "中权重", "参考"
- Conflict text: "⚠ 存在矛盾信号…", "综合权重：", "做多信号胜出", "做空信号胜出"
- Survey timeline: "调研时间线（近90天）", "专程拜访", "开放日", "点越大机构数越多"
- Short-selling text: "空头在加仓", "空头在平仓", "融券余量"
- Participation: "高于均值", "低于均值", "机构参与度", "vs均"
- Prediction form: "你的预测", "往上 ↑", "往下 ↓", "不好说", "加一条备注（可选，80字内）", "✓ 已记录，5天后系统核对"
- Prediction results: "✓ 对了", "✗ 错了", "5日收益 {return}%", "待核对"
- Context descriptions: ~10 blocks describing what each signal means (lines 273–367)

### `templates/watchlist.html`
- D-grade warning banner: "只股票已连续 6 次评为 D 级，建议审视是否继续跟踪"

---

## MEDIUM — visible in detail pages

### `templates/stock/fundamentals.html`
- Company type labels: "指数基金 / ETF", "成长期（未盈利）", "困境股", "银行 / 保险"
- Moat direction: "拓宽", "收窄"

### `templates/stock/letter.html`
- Button: "重新生成信件"
- Trade block keys: "买入区间1", "买入区间2", "减仓区间"

### `templates/performance.html`
- Breadcrumb: "← 我的选股", "算账"
- Page title/subtitle: "算账 · 判断力复盘", "这不是「今天浮盈多少」，而是…"
- Stat labels: "胜率", "平均收益", "评级准确率"
- Section headers: "持有中", "已实现收益"

### `static/js/stock-common.js`
- Export: "📋 导出分析包", "⏳ 生成中…", "✅ 已复制！", "导出失败：", "✕ 关闭"

---

## LOW — admin / CN-only features

### `scripts/fund_rater.py`
- Fund subtype names: "宽基ETF", "行业ETF", "场外宽基", "主动基金", "债券基金", "货币基金"

### `static/js/search-widget.js`
- Line 132: `"股票"` fallback asset type string
