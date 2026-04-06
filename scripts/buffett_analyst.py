"""
股票雷达 · 巴菲特 AI 分析模块
使用 Groq (Llama 3) 免费 API，对每只股票生成结构化巴菲特视角点评
"""

import json, time, requests
from config import BUFFETT_PROFILES, GROQ_API_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.3-70b-versatile"

# ── 日报分析 System Prompt ────────────────────────────
SYSTEM_DAILY = """你是一位严格遵循巴菲特价值投资框架的分析师。

对每只股票给出结构化判断，严格按以下格式输出，不要多余文字：

护城河：[稳固/受压/收窄] | 管理层：[可信/观察/警惕] | 资金：[流入/中性/流出] | 趋势：[改善/稳定/恶化]
结论：[继续持有/暂时观望/需要警惕]
原因：（一句话，不超过25字）

判断规则：
- 护城河「受压/收窄」：竞争对手动作、技术替代、政策打压
- 管理层「警惕」：CEO/CFO离职/减持、盲目并购、财务造假迹象
- 资金「流出」：主力连续净流出超过2日
- 趋势「恶化」：ROE/净利润连续下滑，或今日负面新闻超过2条
- 结论「需要警惕」：任意一项出现「警惕/收窄/流出+恶化」组合
- 噪音直接忽略：技术分析、资金流向日报、涨跌幅排名类新闻"""

# ── 周期分析 System Prompt ────────────────────────────
SYSTEM_PERIOD = """你是一位价值投资分析师，为投资者撰写周期性回顾报告。

分析框架来自巴菲特历年股东信：
1. 护城河变化：过去这段时间，公司竞争优势是变宽了还是变窄了？
2. 管理层资本配置：资本是否被聪明地使用？（回购>分红>并购>囤现金）
3. 业绩质量：现金流和账面利润方向一致吗？ROE趋势如何？
4. 外部威胁评估：行业结构变化、政策风险、竞争格局

输出要求：
- 给每只股票一个「季度信号灯」：🟢继续/🟡观望/🔴警惕
- 用简洁中文，不超过5句话每只股票
- 最后给出整体组合的一句话评价"""


def _call_groq(system: str, user_msg: str, max_tokens: int = 300) -> str:
    """统一的 Groq API 调用，出错返回空字符串。"""
    if not GROQ_API_KEY:
        return ""
    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       MODEL,
                "messages":    [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens":  max_tokens,
                "temperature": 0.25,
            },
            timeout=25,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    ⚠️ Groq: {e}")
        return ""


def analyze_stock(name: str, code: str, news: list, fund_flow: dict, quote: dict) -> str:
    """
    日报分析：结构化3行输出。
    返回格式：
      护城河：X | 管理层：X | 资金：X | 趋势：X
      结论：X
      原因：X
    """
    profile = BUFFETT_PROFILES.get(code, {})
    if not profile or not news:
        return ""

    news_lines = "\n".join(
        f"- {n['title']}（{n.get('source','')}）"
        for n in news[:6]
    )

    ff_str = ""
    if fund_flow:
        net   = fund_flow.get("main_net", 0)
        ratio = fund_flow.get("main_ratio", 0)
        ff_str = f"主力资金净{'流入' if net >= 0 else '流出'} {abs(net):.2f}亿（占比{ratio:.1f}%）"

    price_str = ""
    if quote:
        price_str = f"今日 ¥{quote.get('price', 0):.2f}（{quote.get('change', 0):+.2f}%）"

    user_msg = f"""股票：{name}（{code}）
巴菲特评级：{profile.get('grade', '?')}级
护城河：{profile.get('moat', '')}
近5年ROE：{profile.get('roe_5y', '')}
核心风险：{profile.get('key_risk', '')}
{price_str}
{ff_str}

今日新闻（已过滤噪音）：
{news_lines}

按格式给出分析。"""

    return _call_groq(SYSTEM_DAILY, user_msg, max_tokens=200)


def analyze_period(period_label: str, days: int, news_by_code: dict,
                   quotes_by_code: dict, fund_flows: dict) -> str:
    """
    周期分析（周/月/季）：给整个自选股池生成一份叙述性报告。
    news_by_code: {code: [news items from last N days]}
    """
    from config import WATCHLIST

    stocks_summary = []
    for name, code, _ in WATCHLIST:
        profile = BUFFETT_PROFILES.get(code, {})
        if not profile:
            continue

        stock_news = news_by_code.get(code, [])
        if not stock_news:
            stocks_summary.append(f"**{name}（{code}）**：{period_label}内无实质性新闻")
            continue

        # 过滤噪音
        from config import NOISE_KEYWORDS, POSITIVE_SIGNALS, NEGATIVE_SIGNALS
        real_news = [n for n in stock_news
                     if not any(k in n.get("title", "") for k in NOISE_KEYWORDS)]

        pos = [n["title"][:60] for n in real_news
               if any(k in n.get("title", "") for k in POSITIVE_SIGNALS)]
        neg = [n["title"][:60] for n in real_news
               if any(k in n.get("title", "") for k in NEGATIVE_SIGNALS)]

        ff  = fund_flows.get(code, {})
        ff_str = f"资金净{'流入' if ff.get('main_net', 0) >= 0 else '流出'} {abs(ff.get('main_net', 0)):.1f}亿" if ff else ""
        q   = quotes_by_code.get(code, {})
        pct_str = f"区间涨跌 {q.get('change_pct', 0):+.1f}%" if q else ""

        summary_parts = [f"**{name}（{code}）** {pct_str} {ff_str}"]
        if pos:
            summary_parts.append(f"  正面：{pos[0]}")
        if neg:
            summary_parts.append(f"  负面：{neg[0]}")
        if not pos and not neg and real_news:
            summary_parts.append(f"  中性：{real_news[0]['title'][:60]}")
        stocks_summary.append("\n".join(summary_parts))

    user_msg = f"""请为以下自选股池撰写「{period_label}回顾」（过去{days}天）：

{chr(10).join(stocks_summary)}

请按格式输出：
1. 每只股票一个信号灯（🟢/🟡/🔴）+ 一句评价
2. 最后一行：「组合整体：[稳健/需关注/有风险]——[一句总结]」"""

    return _call_groq(SYSTEM_PERIOD, user_msg, max_tokens=600)


SYSTEM_LETTER = """你是沃伦·巴菲特，用第一人称写一封给持仓者的私人分析信，同时附上结构化维度评估。

【第一部分：分析信正文】
分析框架（贯穿全文，不要列清单）：
1. 生意分类：GREAT（高ROE、低资本消耗）/ GOOD（稳固但需持续再投入）/ GRUESOME（高增长、吃资本、不赚钱）
2. 护城河方向：变宽还是变窄？有没有竞争者逼近、技术替代、政策打压的信号？
3. 管理层信号：机构惰性迹象（高点并购、CFO离职、频繁"一次性费用"）？还是真金白银回购/增持？
4. 资金面（A股）：主力净流入/流出的幅度和趋势说明什么？
5. 估值常识：PE/PB跟历史均值比是便宜还是贵？没数据不猜。

写作要求：
- 开头直接切入最重要的一件事
- 有数据就用，没有就说"数据不足"，不编造
- 该犀利时犀利，不和稀泥
- 偶尔可提查理芒格
- 结尾一句话给出明确立场
- 署名「沃伦·巴菲特（私人版）」
- 总字数 250-350 字（中文），纯文字无 Markdown

【第二部分：结构化维度（信件正文结束后，另起一行）】
在信件最后，必须输出以下格式（每行一个字段，冒号后直接接内容，不超过25字）：

===DIMS===
护城河：[一句话，说明宽/窄/稳及核心依据]
管理层：[一句话，信号正面/中性/有红旗]
估值：[一句话，便宜/合理/偏贵，引用PE/PB数据]
资金流向：[一句话，流入/流出/中性，引用主力数据]
行为金融：[一句话，从Kahneman行为经济学视角——当前持有者最可能犯什么心理偏差？理性人应该怎么看？若是卖出/D级，必须点名沉没成本陷阱]
宏观敏感度：[一句话，对利率/政策/汇率的敏感程度]
评级：[A/B+/B/B-/C/D] | 结论：[买入/持有/减持/卖出]
===END===

行为金融字段由调用方注入上下文提示，你只需基于该提示写一句有力的行为学诊断（≤25字），语气直接，不含糊。"""


def _score_news(news: list) -> list:
    """
    对新闻按信号强度排序，重要的排前面。
    负面信号（CFO离职/减持/亏损）> 正面信号（回购/中标）> 中性
    同级别内按时间倒序。
    """
    HIGH_NEG  = ["辞职", "离职", "被查", "立案", "违规", "处罚", "诉讼", "商誉减值", "暴雷"]
    MID_NEG   = ["减持", "亏损", "下滑", "下降", "降级", "失败", "撤回", "退出"]
    HIGH_POS  = ["回购", "增持", "大额分红", "创历史新高", "重大中标", "获批上市"]
    MID_POS   = ["派息", "分红", "签约", "战略合作", "净利润增长", "获批", "中标"]
    NOISE     = ["只个股", "家公司", "突破年线", "牛熊分界", "资金流向日报",
                 "盘中播报", "技术分析", "K线", "涨跌幅排名"]

    def score(n):
        t = n.get("title", "")
        if any(k in t for k in NOISE):   return -1
        if any(k in t for k in HIGH_NEG): return 5
        if any(k in t for k in MID_NEG):  return 4
        if any(k in t for k in HIGH_POS): return 3
        if any(k in t for k in MID_POS):  return 2
        return 1  # 中性

    scored = [(score(n), n) for n in news]
    filtered = [(s, n) for s, n in scored if s > 0]  # 去噪音
    filtered.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in filtered]


def analyze_stock_v2(code: str, name: str, market: str,
                     price: dict, news: list, fund_flow: dict,
                     fundamentals: dict = None, signals: dict = None) -> dict:
    """
    pipeline 调用的新版分析函数。
    返回 dict，可直接传给 db.save_analysis(**result)。
    """
    today = __import__('datetime').datetime.now(
        __import__('datetime').timezone(__import__('datetime').timedelta(hours=8))
    ).strftime("%Y-%m-%d")

    # 新闻：先排序过滤，再取前8
    sorted_news = _score_news(news)
    news_lines = "\n".join(
        f"- {n.get('title','')[:100]}（{n.get('source','')}）"
        for n in sorted_news[:8]
    ) or "（暂无近期新闻）"

    price_str = ""
    pe_str    = ""
    if price:
        p   = price.get("price")
        chg = price.get("change_pct")
        pe  = price.get("pe_ratio")
        cur = {"nz":"NZD","cn":"CNY","hk":"HKD","us":"USD"}.get(market,"USD")
        if p:
            price_str = f"当前价格：{cur} {p:.2f}（{chg:+.2f}%）" if chg else f"当前价格：{cur} {p:.2f}"
        if pe:
            pe_str = f"市盈率（TTM）：{pe:.1f}x"

    ff_str = ""
    if fund_flow and market == "cn":
        net   = fund_flow.get("main_net", 0)
        ratio = fund_flow.get("main_ratio", 0)
        ff_str = f"主力资金净{'流入' if net>=0 else '流出'} {abs(net):.2f}亿（占比{ratio:+.1f}%）"

    # 从 BUFFETT_PROFILES 拿档案背景（如果有）
    from config import BUFFETT_PROFILES
    profile    = BUFFETT_PROFILES.get(code, {})
    grade_bg   = profile.get("grade", "")
    moat_bg    = profile.get("moat", "")
    roe_bg     = profile.get("roe_5y", "")
    risk_bg    = profile.get("key_risk", "")
    biz_type   = profile.get("biz_type", "")

    margin_bg  = profile.get("net_margin_trend", "")

    profile_lines = []
    if grade_bg:  profile_lines.append(f"历史评级参考：{grade_bg}级")
    if biz_type:  profile_lines.append(f"生意类型：{biz_type}")
    if moat_bg:   profile_lines.append(f"护城河：{moat_bg}")
    if roe_bg:    profile_lines.append(f"近5年ROE：{roe_bg}")
    if margin_bg: profile_lines.append(f"净利率趋势：{margin_bg}")
    if risk_bg:   profile_lines.append(f"核心风险：{risk_bg}")
    profile_str = "\n".join(profile_lines)

    # 财务数据上下文
    fund_lines = []
    if fundamentals:
        annual = fundamentals.get("annual", [])
        if annual:
            fund_lines.append("近年财务数据（年报）：")
            for row in annual[:5]:  # 最近5年
                yr = row.get("year", "")
                parts = []
                if row.get("roe") not in (None, "False", "nan", ""):
                    parts.append(f"ROE {row['roe']}")
                if row.get("net_margin") not in (None, "False", "nan", ""):
                    parts.append(f"净利率 {row['net_margin']}")
                if row.get("debt_ratio") not in (None, "False", "nan", ""):
                    parts.append(f"负债率 {row['debt_ratio']}")
                if row.get("profit_growth") not in (None, "False", "nan", ""):
                    parts.append(f"净利润增长 {row['profit_growth']}")
                if parts:
                    fund_lines.append(f"  {yr}: {', '.join(parts)}")

        # 判断是否亏损（最新年 ROE < 0 或净利润增长为大幅负值）
        latest_annual = annual[0] if annual else {}
        def _pct_val(s):
            try: return float(str(s).replace('%','').strip())
            except: return None
        latest_roe = _pct_val(latest_annual.get('roe',''))
        is_loss_making = (latest_roe is not None and latest_roe < 0)

        pe_now = fundamentals.get("pe_current")
        pe_pct = fundamentals.get("pe_percentile_5y")
        pb_now = fundamentals.get("pb_current")
        pb_pct = fundamentals.get("pb_percentile_5y")

        if is_loss_making:
            # 亏损公司：PE 无意义，明确告诉 LLM
            fund_lines.append("⚠️ 估值注意：公司当前ROE为负（亏损状态），PE指标无意义，不可用于估值判断。")
            fund_lines.append("  请聚焦于：何时能扭亏、资产负债表能否支撑、管理层是否有可信的转型计划。")
            if pb_now and pb_pct is not None:
                cheap_pb = "偏低" if pb_pct < 30 else ("偏高" if pb_pct > 70 else "历史中位")
                fund_lines.append(f"  PB {pb_now}x（5年历史{pb_pct}%分位，{cheap_pb}）——亏损时PB是主要参考锚")
        else:
            if pe_now and pe_pct is not None:
                cheap = "偏低估" if pe_pct < 30 else ("偏高估" if pe_pct > 70 else "处于历史中位")
                fund_lines.append(f"估值：PE {pe_now}x（5年历史{pe_pct}%分位，{cheap}）")
            if pb_now and pb_pct is not None:
                fund_lines.append(f"       PB {pb_now}x（5年历史{pb_pct}%分位）")

    fundamentals_str = "\n".join(fund_lines)

    # 华尔街级信号
    signals_lines = []
    if signals:
        pledge = signals.get("pledge_ratio")
        if pledge is not None:
            flag = " ⚠️ 超40%高风险" if pledge > 40 else (" 注意" if pledge > 20 else "")
            signals_lines.append(f"大股东质押比例：{pledge:.1f}%{flag}")

        mb = signals.get("margin_balance")
        mc_pct = signals.get("margin_change_pct")
        mdir = signals.get("margin_direction", "")
        if mb is not None:
            signals_lines.append(f"融资余额：{mb/1e8:.2f}亿（近5日{mdir}{abs(mc_pct or 0):.1f}%）")

        moat_dir = signals.get("moat_direction")
        if moat_dir:
            signals_lines.append(f"护城河方向（量化推算）：{moat_dir}")

        # ROIC 趋势（预计算方向标签，不让 LLM 自己推断数字大小）
        roic_trend = signals.get("roic_trend", [])
        if roic_trend:
            roic_str = " → ".join(f"{r['year']}:{r['roic']}%" for r in roic_trend[:5])
            # 计算近2年方向
            if len(roic_trend) >= 2:
                r_new = roic_trend[0]["roic"]
                r_old = roic_trend[1]["roic"]
                delta = r_new - r_old
                if delta >= 2:
                    roic_dir = f"↑ 近2年回升（+{delta:.1f}pp）"
                elif delta <= -2:
                    roic_dir = f"↓ 近2年下滑（{delta:.1f}pp）"
                else:
                    roic_dir = "→ 近2年基本持平"
                # 5年最高点
                roic_peak = max(r["roic"] for r in roic_trend)
                peak_year = next(r["year"] for r in roic_trend if r["roic"] == roic_peak)
                vs_peak = "已接近历史高位" if r_new >= roic_peak * 0.85 else f"仍低于{peak_year}年峰值{roic_peak}%"
                signals_lines.append(
                    f"ROIC（投入资本回报率）：{roic_str}"
                    f"\n  → 趋势判断：{roic_dir}，{vs_peak}"
                )
            else:
                signals_lines.append(f"ROIC：{roic_str}")

        # Owner Earnings（同样预计算方向）
        oe_list = signals.get("owner_earnings", [])
        if oe_list:
            latest_oe = oe_list[0]
            oe_str = f"{latest_oe['oe_bn']}亿（OCF {latest_oe['ocf_bn']}亿 - CapEx {latest_oe['capex_bn']}亿）"
            signals_lines.append(f"Owner Earnings（最新{latest_oe['year']}）：{oe_str}")
            if len(oe_list) >= 2:
                oe_new = oe_list[0]["oe_bn"]
                oe_old = oe_list[1]["oe_bn"]
                oe_delta = oe_new - oe_old
                oe_dir = f"↑ 同比+{oe_delta:.1f}亿" if oe_delta > 0 else f"↓ 同比{oe_delta:.1f}亿"
                signals_lines.append(f"  → Owner Earnings 趋势：{oe_dir}（{oe_list[1]['year']}:{oe_old}亿 → {oe_list[0]['year']}:{oe_new}亿）")

        # 留存利润检验
        re_eff = signals.get("retained_efficiency")
        re_eq  = signals.get("retained_equity_change")
        re_np  = signals.get("retained_total_profit")
        if re_eff is not None:
            if re_eff >= 1.0:
                re_verdict = "✓ 优秀：每留1元利润，股东权益增加超过1元，管理层在为股东创造价值"
            elif re_eff >= 0.6:
                re_verdict = "○ 良好：每留1元利润，股东权益增加约{:.2f}元（部分通过分红返还股东）".format(re_eff)
            else:
                re_verdict = "✗ 偏低：每留1元利润，股东权益仅增加{:.2f}元，需关注资本配置效率".format(re_eff)
            signals_lines.append(
                f"留存利润检验（近5年）：{re_verdict}"
                f"\n  数据：权益增加{re_eq}亿 ÷ 利润合计{re_np}亿 = {re_eff:.2f}"
            )

        inst_inc = signals.get("inst_increased")
        inst_dec = signals.get("inst_decreased")
        inst_total = signals.get("inst_total")
        if inst_total:
            net_sig = "净增持" if (inst_inc or 0) > (inst_dec or 0) else ("净减持" if (inst_dec or 0) > (inst_inc or 0) else "持平")
            signals_lines.append(f"机构持仓：共{inst_total}家，增持{inst_inc}/减持{inst_dec}，{net_sig}")
            top = signals.get("inst_top", [])
            if top:
                top_str = "；".join(
                    f"{t['name']}({t['type']}){'+' if t['change']>=0 else ''}{t['change']:.2f}pp"
                    for t in top[:3]
                )
                signals_lines.append(f"  主要机构：{top_str}")

        fcf = signals.get("fcf_quality_avg")
        if fcf is not None:
            quality = "良好" if fcf >= 0.8 else ("偏低" if fcf >= 0.5 else "差——利润质量存疑")
            signals_lines.append(f"FCF质量（现金流/净利润）：均值{fcf:.2f}x，{quality}")

    signals_str = "\n".join(signals_lines)

    # ST 股检测
    is_st = "ST" in name.upper() or code.upper().startswith(("ST", "*ST"))
    st_warning = "\n⚠️ 风险警示：该股票为ST/风险警示股，存在退市风险，流动性差，散户占比极高，属于典型彩票型资产。" if is_st else ""

    # 预计算行为金融提示（互斥，优先级：ST > 大幅流出 > 近期急涨 > 默认）
    ff_ratio   = fund_flow.get("main_ratio", 0)  if fund_flow else 0
    change_pct = price.get("change_pct",    0)   if price     else 0
    if is_st:
        behavioral_hint = "ST彩票型资产：持有者多为损失厌恶（亏损不甘止损），而非价值判断。诊断这一心理陷阱。"
    elif ff_ratio is not None and ff_ratio < -5:
        behavioral_hint = "主力资金大幅净流出（机构在离场）。从行为经济学角度，散户此时接盘是典型的'博傻'心理，诊断这一现象。"
    elif change_pct is not None and change_pct > 15:
        behavioral_hint = "近期急涨超15%。分析FOMO（错失恐惧）追涨情绪——Kahneman的'系统1思维'在发挥作用。"
    else:
        behavioral_hint = "常规持有状态。分析投资者最常见的锚定效应（以买入价而非内在价值为参考锚）。"

    user_msg = f"""公司：{name}（{code}）
市场：{market.upper()}{st_warning}
{price_str}
{ff_str}
{profile_str}
{fundamentals_str}
{signals_str}

近期新闻（已过滤噪音，按信号重要性排序）：
{news_lines}

行为金融提示（仅用于 ===DIMS=== 中的「行为金融」字段）：{behavioral_hint}

请按格式输出：先写分析信正文，再输出 ===DIMS=== 结构化维度块。"""

    raw = _call_groq(SYSTEM_LETTER, user_msg, max_tokens=900)
    if not raw:
        return {}

    import re

    # 分离信件正文和维度块（===END=== 可选，兼容 LLM 省略结尾标记）
    dims_match = re.search(r'===DIMS===(.*?)(?:===END===|$)', raw, re.DOTALL)
    if dims_match:
        dims_text   = dims_match.group(1).strip()
        letter_text = raw[:dims_match.start()].strip()
    else:
        dims_text   = ""
        letter_text = raw.strip()

    # 从信件正文里也去掉评级行（兼容旧格式）
    letter_lines = [l for l in letter_text.splitlines()
                    if not re.match(r'\s*评级[：:]\s*[A-Z]', l)]
    letter_text = "\n".join(letter_lines).strip()

    # 解析评级和结论
    grade, conclusion = "C", "持有"
    grade_line = dims_text if dims_text else raw
    m = re.search(r'评级[：:]\s*([A-Z][+\-]?)', grade_line)
    if m: grade = m.group(1)
    m2 = re.search(r'结论[：:]\s*(买入|持有|减持|卖出)', grade_line)
    if m2: conclusion = m2.group(1)

    # 解析各维度
    def _parse_dim(key: str, text: str) -> str:
        m = re.search(rf'{key}[：:]\s*(.+)', text)
        return m.group(1).strip()[:60] if m else ""

    dims = {
        "moat":             _parse_dim("护城河", dims_text),
        "management":       _parse_dim("管理层", dims_text),
        "valuation":        _parse_dim("估值",   dims_text),
        "fund_flow_summary":_parse_dim("资金流向", dims_text),
        "behavioral":       _parse_dim("行为金融", dims_text),
        "macro_sensitivity":_parse_dim("宏观敏感度", dims_text),
    }

    # 卖出/减持结论时，确保行为金融字段包含沉没成本提示
    if conclusion in ("卖出", "减持") and dims.get("behavioral"):
        if "沉没" not in dims["behavioral"] and "成本" not in dims["behavioral"]:
            dims["behavioral"] = "忘记买入成本——今天愿意以此价格买入吗？若答案是否，持有的唯一理由是情绪，不是价值。"

    return {
        "conclusion":       conclusion,
        "grade":            grade,
        "reasoning":        letter_text[:200],
        "letter_html":      letter_text,
        "raw_output":       raw,
        **dims,
    }


def analyze_all(data: dict) -> dict:
    """
    日报：分析所有自选股，返回 {code: analysis_text}。
    Groq 免费版限速 30 RPM，每次请求后等 2 秒。
    """
    from config import WATCHLIST
    results      = {}
    news_map      = data.get("news", {})
    fund_flow_map = data.get("fund_flow", {})
    quotes_map    = data.get("quotes", {})

    for name, code, _ in WATCHLIST:
        stock_news = news_map.get(code, [])
        if not stock_news:
            continue

        print(f"    🤖 分析 {name}...")
        text = analyze_stock(
            name      = name,
            code      = code,
            news      = stock_news,
            fund_flow = fund_flow_map.get(code, {}),
            quote     = quotes_map.get(code, {}),
        )
        if text:
            results[code] = text
        time.sleep(2)

    return results
