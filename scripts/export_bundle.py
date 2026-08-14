"""
股票分析数据包导出器
把某只股票的所有数据整合成一个 Markdown 文档 + 分析指令
可直接粘贴给 Claude / ChatGPT 进行深度分析
"""

import json
from datetime import datetime, timezone, timedelta
from scripts.buffett_utils import summarize_to_sentence

CN_TZ = timezone(timedelta(hours=8))
_FRAMEWORK_LABELS = {
    "distressed": "困境重整",
    "speculative": "高风险投机",
    "financial": "金融机构",
    "cyclical": "周期股",
    "utility": "高股息/公用事业",
    "growth_tech": "成长/科技",
    "pre_profit": "未盈利企业",
    "etf": "ETF/指数基金",
    "mature_value": "成熟价值股",
}


def _fmt_annual(annual: list) -> str:
    if not annual:
        return "（无历史财务数据）"
    rows = ["| 年份 | 营收(亿) | 净利润(亿) | ROE | 净利率 | 负债率 |",
            "|------|---------|----------|-----|------|------|"]
    for y in annual[:6]:
        rows.append(
            f"| {y.get('year','?')} "
            f"| {y.get('revenue','—')} "
            f"| {y.get('net_profit','—')} "
            f"| {y.get('roe','—')}% "
            f"| {y.get('net_margin','—')}% "
            f"| {y.get('debt_ratio','—')}% |"
        )
    return "\n".join(rows)


def _fmt_news(news: list) -> str:
    if not news:
        return "（近期无新闻）"
    lines = []
    for i, n in enumerate(news[:20], 1):
        pub = str(n.get("publish_time", n.get("fetched_date", "")))[:10]
        title = n.get("title", "")[:100]
        source = n.get("source", "")
        mismatch = " ⚠️[非本公司，已降权]" if n.get("entity_mismatch") else ""
        lines.append(f"{i}. [{pub}] {title}（{source}）{mismatch}")
    return "\n".join(lines)


def _fmt_events(events: list) -> str:
    if not events:
        return "（无事件记录）"
    lines = []
    type_labels = {
        "st_trigger": "被ST",
        "st_lifted": "摘ST",
        "restructuring_announced": "重整方案发布",
        "restructuring_vote": "债权人表决",
        "restructuring_approved": "重整获批",
        "rights_issue": "配股",
        "bonus_share": "送转股",
        "name_change": "股票更名",
        "delist_warning": "退市风险警示",
        "delist_final": "终止上市",
        "major_shareholder_change": "大股东变更",
        "scheme_risk": "方案风险",
    }
    for ev in events:
        label = type_labels.get(ev.get("event_type", ""), ev.get("event_type", ""))
        date = ev.get("event_date", "")
        summary = ev.get("summary", "")
        lines.append(f"- **{label}** ({date}): {summary}")
    return "\n".join(lines)


def _get_analysis_prompt(company_type: str, name: str, code: str) -> str:
    framework = _FRAMEWORK_LABELS.get(company_type or "mature_value", "价值投资")
    base = f"""---
## 分析指令（将此文档完整粘贴给 Claude / ChatGPT）

你是一位专业的 A 股分析师，擅长 **{framework}** 框架。

以上是 **{name}（{code}）** 的完整数据包，请给出结构化分析：
"""
    if company_type == "distressed":
        return base + """
1. **重整进度评估**：当前走到哪一步？距最终落地还有哪些关键节点？
2. **催化剂耗尽判断**：主要利好（重整宣布/债权人通过）是否已被股价充分定价？
3. **稀释风险量化**：转增/配股后现有股东实际持股价值缩水多少%？
4. **暂停上市风险**：接下来几个月有没有被暂停交易的可能？
5. **概率加权分析**：
   - 重整成功（概率X%）→ 合理估值 ¥Y，现价收益Z%
   - 重整失败（概率X%）→ 跌至 ¥Y，现价亏损Z%
   - 期望收益 = 加权平均
6. **具体操作建议**：持有/出场/止损线在哪？截止时间？

请用数字说话，避免模糊表达。
"""
    elif company_type == "growth_tech":
        return base + """
1. **营收增速趋势**：CAGR 多少？加速还是减速？
2. **毛利率方向**：规模扩张时毛利率有没有提升？
3. **研发效率**：研发投入占比 vs 新产品/市场产出
4. **市场空间**：TAM 还有多大？当前渗透率？
5. **护城河类型**：网络效应/技术壁垒/品牌/低价，哪个支撑？
6. **估值合理性**：当前 PS/PE/PB 对比历史分位，溢价合理吗？
7. **结论**：买入/持有/减持，目标价区间？

请给出具体数字，不要泛泛而谈。
"""
    elif company_type in ("cyclical",):
        return base + """
1. **周期位置**：行业现在在上行还是下行周期？库存处于什么水平？
2. **大宗价格**：关键原材料/产品价格趋势如何影响利润？
3. **自由现金流**：能不能熬过最坏的时候？
4. **管理层信号**：高点扩产还是低点回购？
5. **估值逻辑**：现在的 PB 处于历史几%分位？
6. **入场/出场时机**：现在是周期哪个位置？适合买入吗？

请对比历史数据，给出有依据的判断。
"""
    else:
        return base + """
1. **护城河评估**：是变宽还是变窄？用具体数据支撑
2. **管理层质量**：回购/派息/并购历史，对股东好吗？
3. **盈利质量**：现金流 vs 账面利润是否一致？ROE 趋势？
4. **估值判断**：PE/PB 对比历史分位，当前是高估/合理/低估？
5. **主要风险**：最可能损害护城河的1-2个外部威胁
6. **结论**：买入/持有/减持，最关键的1-2个理由？

请用巴菲特视角，用数字说话，不要用模糊词。
"""


def build_export_bundle(code: str, user_id: int = None) -> dict:
    """
    构建单只股票的完整分析数据包。
    返回 {"markdown": str, "stock_name": str, "framework": str}
    """
    import db

    stock = db.get_stock(code)
    if not stock:
        return {"error": "股票不存在"}

    name = stock.get("name", code)
    market = stock.get("market", "cn")

    price = db.get_latest_price(code) or {}
    fundamentals = db.get_fundamentals(code) or {}
    news = db.get_stock_news(code, days=30)
    events = db.get_stock_events(code, limit=20)
    latest_analysis = db.get_latest_analysis(code) or {}
    meta = db.get_stock_meta(code) or {}
    company_type = meta.get("company_type", "mature_value")
    fund_flow = db.get_fund_flow(code) if market == "cn" else {}

    # 持仓成本（如果有）
    entry_info = ""
    if user_id:
        try:
            with db.get_conn() as c:
                row = c.execute(
                    "SELECT buy_price, buy_date FROM user_watchlist WHERE user_id=:uid AND stock_code=:code",
                    {"uid": user_id, "code": code},
                ).fetchone()
                if row and row["buy_price"]:
                    cur = price.get("price")
                    cost = float(row["buy_price"])
                    try:
                        pnl = round((float(cur) - cost) / cost * 100, 1) if (cur is not None and cost) else None
                    except (TypeError, ValueError):
                        pnl = None
                    pnl_str = f"（浮{'+' if pnl >= 0 else ''}{pnl}%）" if pnl is not None else ""
                    entry_info = f"\n- 持仓成本：¥{cost}（{row['buy_date']}买入）{pnl_str}"
        except Exception:
            pass

    # 财务数据
    try:
        annual = json.loads(fundamentals.get("annual_json") or "[]")
    except Exception:
        annual = []

    # 价格信息
    cur_price = price.get("price", "—")
    chg = price.get("change_pct")
    chg_str = f"（{'+' if chg >= 0 else ''}{chg:.2f}%）" if chg is not None else ""
    pe = fundamentals.get("pe_current", "—")
    pb = fundamentals.get("pb_current", "—")

    # 资金流向
    ff_str = ""
    if fund_flow:
        net = fund_flow.get("main_net", 0)
        ratio = fund_flow.get("main_ratio", 0)
        ff_str = f"\n- 主力资金：净{'流入' if net >= 0 else '流出'} {abs(net):.2f}亿（{ratio:+.1f}%）"

    # 最新系统分析摘要
    sys_analysis = ""
    if latest_analysis:
        grade = latest_analysis.get("grade", "—")
        conclusion = latest_analysis.get("conclusion", "—")
        reasoning = summarize_to_sentence(latest_analysis.get("reasoning") or "")
        framework_used = latest_analysis.get("framework_used", "—")
        analysis_date = latest_analysis.get("analysis_date", "—")
        sys_analysis = f"""
## 系统最新分析（Groq/LLM生成，{analysis_date}）
- 评级：{grade}级 · 结论：{conclusion}
- 使用框架：{framework_used}
- 摘要：{reasoning}
"""

    framework_label = _FRAMEWORK_LABELS.get(company_type, "价值投资")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")

    markdown = f"""# 股票分析数据包：{name}（{code}）
> 导出时间：{now} | 框架分类：{framework_label}

## 基本信息
- 代码：{code}（{market.upper()}）
- 当前价：¥{cur_price}{chg_str}
- PE：{pe}x | PB：{pb}x{ff_str}{entry_info}

## 5年财务数据
{_fmt_annual(annual)}

## 近期新闻（最近30天，共{len(news)}条）
{_fmt_news(news)}

## 重大事件记录
{_fmt_events(events)}
{sys_analysis}
{_get_analysis_prompt(company_type, name, code)}"""

    return {
        "markdown": markdown,
        "stock_name": name,
        "framework": framework_label,
        "company_type": company_type,
    }
