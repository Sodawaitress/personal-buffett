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


SYSTEM_LETTER = """你是沃伦·巴菲特。用第一人称、自信而冷静的语气写分析信。

【核心原则】
写得像在给朋友讲投资逻辑——清晰、有深度、会质疑。不是报告，是思考过程的展现。

【结构（必须包含）】
1. 开头：一句核心判断（如"这家公司陷入困境"或"护城河在加固"）
2. 基本面分析：用数字说话
   - 赚钱能力（ROE、利润率、现金流）
   - 竞争优势（护城河是宽/窄/变窄/变宽）
   - 管理层信号（回购、派息、离职等关键行动）
3. 估值判断：PE/PB对标，当前是高估/合理/低估，52周位置的风险
4. 新闻权重：情绪值、关键信号、对基本面的实际影响（往往被高估）
5. 结尾：一句明确立场（买入/持有/减持/卖出），理由是什么

【数据准则】
- 有数据就用，会变得有说服力（"净利率-0.5%"比"利润下滑"有力100倍）
- 没有数据就直说"数据不足"，不要编造
- 对比是核心：不是看绝对值，是看 vs 历史、vs 同行、vs 债券收益率
- 关键数字要加粗或强调，但不要写"数据显示"这种填充词

【巴菲特式质疑】
当看到好消息时，问自己：
- "但这改变了基本面的坏处吗？"
- "这是真的竞争优势还是一次性利好？"
- "管理层这个决定对我有利吗？"

【🚨 红旗检查清单（必须提及）】
如果提供的数据中包含以下任何一项，必须在分析中明确指出，不能忽视：
- ROE < 5% 或 ROE < 0（赚钱能力弱或亏损）→ 必须说"赚钱能力几乎为零"
- 净利率 < 0%（公司在亏损）→ 必须说"公司在烧钱"
- 债务比 > 20（高杠杆）→ 必须说"高杠杆风险"
- 52周价格位置 > 90%（接近年高）→ 必须说"风险位置"
- 护城河变窄（市占率下降等）→ 必须说"竞争地位恶化"
- 情绪值 < -0.5 或关键负面信号 → 必须量化提及

这些红旗不能被好消息（如新闻利好、战略合作）所掩盖。
好消息最多只能"部分抵消"这些风险，不能"消除"它们。

【禁止】
- 模糊词：不要说"较强""相对好"，说"是否比对手强"
- 空承诺：不要说"值得关注"，说"值不值得现在买"
- 编造数据：没有就说没有，宁可简洁也不要虚构
- 超过 400 字：言简意赅是高手

【输出格式】
自然段落，但最后一段务必是：
「基于以上，我的判断是：[买入/持有/减持/卖出]。因为[最关键的1-2个因素]。」
"""


def _analyze_news_signals(news: list) -> dict:
    """
    从新闻中提取量化信号：
    返回 {
        "sentiment_avg": float (-1 ~ +1),           # 平均情绪
        "signal_count": {"high_pos": int, "high_neg": int, "mid_pos": int, "mid_neg": int},
        "key_signals": ["CFO离职", "回购¥10亿", ...],  # 关键信号列表
        "impact_score": float (0-10),                # 对股价的预测影响力（0=无 10=极高）
        "momentum": "accelerating" | "stable" | "decelerating",  # 信号动态
        "summary": "..."                             # 新闻总结一句话
    }
    """
    # 中文关键词
    HIGH_NEG  = ["辞职", "离职", "被查", "立案", "违规", "处罚", "诉讼", "商誉减值", "暴雷"]
    MID_NEG   = ["减持", "亏损", "下滑", "下降", "降级", "失败", "撤回", "退出"]
    HIGH_POS  = ["回购", "增持", "大额分红", "创历史新高", "重大中标", "获批上市"]
    MID_POS   = ["派息", "分红", "签约", "战略合作", "净利润增长", "获批", "中标"]
    NOISE     = ["只个股", "家公司", "突破年线", "牛熊分界", "资金流向日报",
                 "盘中播报", "技术分析", "K线", "涨跌幅排名"]

    # 英文关键词（用于摩根大通等英文新闻源）
    EN_HIGH_NEG = ["resign", "fired", "scandal", "lawsuit", "fraud", "downgrade",
                   "investigation", "bankruptcy", "loss", "crisis", "collapse"]
    EN_MID_NEG = ["decline", "miss", "lower", "reduce", "weak", "challenge", "concern"]
    EN_HIGH_POS = ["upgrade", "acquisition", "record profit", "breakthrough", "approval",
                   "deal", "expansion", "beat estimate"]
    EN_MID_POS = ["partnership", "growth", "earnings", "profit", "revenue", "profit"]

    signal_counts = {"high_neg": 0, "mid_neg": 0, "high_pos": 0, "mid_pos": 0}
    sentiments = []
    key_signals = []
    impact_scores = []

    for n in news:
        title = n.get("title", "").lower()  # 转小写便于英文匹配

        # 过滤噪音
        if any(k in title for k in NOISE):
            continue

        # 信号分类（先检查中文，再检查英文）
        if any(k in title for k in HIGH_NEG) or any(k in title for k in EN_HIGH_NEG):
            signal_counts["high_neg"] += 1
            sentiments.append(-1.0)
            impact_scores.append(8)
            key_signals.append(next((k for k in HIGH_NEG if k in title),
                                   next((k for k in EN_HIGH_NEG if k in title), "负面信号")))
        elif any(k in title for k in MID_NEG) or any(k in title for k in EN_MID_NEG):
            signal_counts["mid_neg"] += 1
            sentiments.append(-0.5)
            impact_scores.append(5)
            key_signals.append(next((k for k in MID_NEG if k in title),
                                   next((k for k in EN_MID_NEG if k in title), "中性负面")))
        elif any(k in title for k in HIGH_POS) or any(k in title for k in EN_HIGH_POS):
            signal_counts["high_pos"] += 1
            sentiments.append(1.0)
            impact_scores.append(7)
            key_signals.append(next((k for k in HIGH_POS if k in title),
                                   next((k for k in EN_HIGH_POS if k in title), "正面信号")))
        elif any(k in title for k in MID_POS) or any(k in title for k in EN_MID_POS):
            signal_counts["mid_pos"] += 1
            sentiments.append(0.5)
            impact_scores.append(3)
            key_signals.append(next((k for k in MID_POS if k in title),
                                   next((k for k in EN_MID_POS if k in title), "中性正面")))
        else:
            sentiments.append(0.0)
            impact_scores.append(1)

    # 计算综合指标
    sentiment_avg = sum(sentiments) / len(sentiments) if sentiments else 0.0
    impact_score = sum(impact_scores) / len(impact_scores) if impact_scores else 0.0

    # 动态判断：正负信号的趋势
    neg_count = signal_counts["high_neg"] + signal_counts["mid_neg"]
    pos_count = signal_counts["high_pos"] + signal_counts["mid_pos"]

    if neg_count > pos_count * 1.5:
        momentum = "accelerating_negative"  # 负面加速
    elif pos_count > neg_count * 1.5:
        momentum = "accelerating_positive"  # 正面加速
    else:
        momentum = "stable"  # 平衡

    # 生成摘要
    if key_signals:
        summary = f"最近关键信号：{', '.join(set(key_signals[:3]))}"
    else:
        summary = "暂无重大信号"

    return {
        "sentiment_avg": round(sentiment_avg, 2),
        "signal_count": signal_counts,
        "key_signals": list(set(key_signals[:5])),  # 去重，最多5个
        "impact_score": round(impact_score, 1),
        "momentum": momentum,
        "summary": summary,
    }


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

    def sentiment(n):
        """返回 sentiment 分值：-1（负）/ 0（中性）/ 1（正）"""
        score_val = score(n)
        if score_val in (5, 4):
            return -1.0  # 负面
        elif score_val in (3, 2):
            return 1.0   # 正面
        elif score_val == 1:
            return 0.0   # 中性
        else:
            return 0.0   # 噪音当中性处理

    scored = [(score(n), n) for n in news]

    # 同时更新新闻的 sentiment 字段（供后续存储）
    import db
    for s, n in scored:
        if s > 0:  # 只对有效新闻计算情绪
            n_sentiment = sentiment(n)
            # 尝试更新数据库（如果新闻已存在）
            try:
                with db.get_conn() as c:
                    c.execute(
                        "UPDATE stock_news SET sentiment=? WHERE id=?",
                        (n_sentiment, n.get("id"))
                    )
            except:
                pass  # 如果更新失败，继续处理

    filtered = [(s, n) for s, n in scored if s > 0]  # 去噪音
    filtered.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in filtered]


def analyze_stock_v2(code: str, name: str, market: str,
                     price: dict, news: list, fund_flow: dict,
                     fundamentals: dict = None, signals: dict = None,
                     entry_price: float = None, buy_date: str = None) -> dict:
    """
    pipeline 调用的新版分析函数。
    返回 dict，可直接传给 db.save_analysis(**result)。
    """
    today = __import__('datetime').datetime.now(
        __import__('datetime').timezone(__import__('datetime').timedelta(hours=8))
    ).strftime("%Y-%m-%d")

    # 新闻：先排序过滤，再取前8
    # 新闻量化分析
    sorted_news = _score_news(news)
    news_signals = _analyze_news_signals(news)

    # 新闻显示（带情绪标签）
    news_lines_list = []
    for n in sorted_news[:8]:
        title = n.get('title','')[:100]
        source = n.get('source','')
        sentiment = n.get('sentiment')

        # 添加情绪标签
        if sentiment is not None:
            if sentiment > 0.5:
                emoji = "📈"  # 正面
            elif sentiment < -0.5:
                emoji = "📉"  # 负面
            else:
                emoji = "➖"  # 中性
        else:
            emoji = "📰"

        news_lines_list.append(f"{emoji} {title}（{source}）")

    news_lines = "\n".join(news_lines_list) or "（暂无近期新闻）"

    # 新闻量化摘要
    news_summary = f"""
【新闻量化信号】
- 情绪平均值：{news_signals['sentiment_avg']}（-1为极负，+1为极正）
- 关键信号：{', '.join(news_signals['key_signals']) if news_signals['key_signals'] else '无'}
- 信号计数：高正面{news_signals['signal_count']['high_pos']}条 | 中正面{news_signals['signal_count']['mid_pos']}条 | 中负面{news_signals['signal_count']['mid_neg']}条 | 高负面{news_signals['signal_count']['high_neg']}条
- 影响力评分：{news_signals['impact_score']}/10（0=无 10=极高）
- 动态趋势：{news_signals['momentum']}（accelerating_positive/stable/accelerating_negative）
- 总结：{news_signals['summary']}
"""

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
            if pb_now:
                if pb_pct is not None:
                    cheap_pb = "偏低" if pb_pct < 30 else ("偏高" if pb_pct > 70 else "历史中位")
                    fund_lines.append(f"  PB {pb_now}x（5年历史{pb_pct}%分位，{cheap_pb}）——亏损时PB是主要参考锚")
                else:
                    fund_lines.append(f"  PB {pb_now}x（历史数据不足）——亏损时PB是主要参考锚")
        else:
            if pe_now is not None:
                if pe_pct is not None:
                    cheap = "偏低估" if pe_pct < 30 else ("偏高估" if pe_pct > 70 else "处于历史中位")
                    fund_lines.append(f"估值：PE {pe_now}x（5年历史{pe_pct}%分位，{cheap}）")
                else:
                    fund_lines.append(f"估值：PE {pe_now}x（历史数据不足）")
            if pb_now is not None:
                if pb_pct is not None:
                    fund_lines.append(f"       PB {pb_now}x（5年历史{pb_pct}%分位）")
                else:
                    fund_lines.append(f"       PB {pb_now}x（历史数据不足）")

    fundamentals_str = "\n".join(fund_lines)

    # 华尔街级信号
    signals_lines = []

    # 非A股的通用财务指标（来自 signals）
    if signals and market != "cn":
        metric_lines = []
        red_flags = []  # 关键风险指标单独列出

        # ROE
        roe = signals.get("roe")
        if roe is not None:
            roe_pct = roe * 100
            if roe_pct < 5:
                red_flags.append(f"🚨 ROE 仅 {roe_pct:.2f}%（赚钱能力几乎为零）")
            else:
                metric_lines.append(f"  ROE（股东权益回报率）：{roe_pct:.2f}%")

        # 利润率
        pm = signals.get("profit_margin")
        if pm is not None:
            pm_pct = pm * 100
            if pm_pct < 0:
                red_flags.append(f"🚨 净利率 {pm_pct:.2f}%（公司在亏损烧钱）")
            else:
                metric_lines.append(f"  净利率：{pm_pct:.2f}%")

        # 毛利率
        gm = signals.get("gross_margin")
        if gm is not None:
            gm_pct = gm * 100
            metric_lines.append(f"  毛利率：{gm_pct:.2f}%")

        # 债务比
        de = signals.get("debt_to_equity")
        if de is not None:
            if de > 20:
                red_flags.append(f"🚨 债务比 {de:.2f}x（极度高杠杆，融资风险高）")
            else:
                metric_lines.append(f"  债务比（D/E）：{de:.2f}x")

        # 流动比
        cr = signals.get("current_ratio")
        if cr is not None:
            metric_lines.append(f"  流动比：{cr:.2f}x")

        # 52周价格位置
        pos = signals.get("price_position")
        if pos is not None:
            pos_pct = pos
            if pos_pct >= 90:
                red_flags.append(f"📊 52周价格位置 {pos_pct:.1f}%（接近年高，买入风险大）")
            elif pos_pct <= 10:
                metric_lines.append(f"  📊 52周价格位置：{pos_pct:.1f}%（接近年低，买入机会）")
            else:
                metric_lines.append(f"  📊 52周价格位置：{pos_pct:.1f}%")

        # 先显示红旗（强制 LLM 关注）
        if red_flags:
            signals_lines.append("【⚠️ 关键风险指标】")
            signals_lines.extend(red_flags)

        # 再显示普通指标
        if metric_lines:
            signals_lines.append("【财务指标概览】")
            signals_lines.extend(metric_lines)

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

    # 技术支撑位
    tech = signals.get("technicals", {}) if signals else {}
    tech_lines = []
    if tech:
        current_price = price.get("price") if price else None
        ma_labels = [("ma250", "年线MA250"), ("ma120", "半年线MA120"),
                     ("ma60", "季线MA60"),   ("ma20", "月线MA20")]
        for key, label in ma_labels:
            val = tech.get(key)
            pct = tech.get(f"price_vs_{key}")
            if val is not None and pct is not None:
                pos = "高于" if pct >= 0 else "低于"
                tech_lines.append(f"{label}：¥{val}，现价{pos}{abs(pct):.1f}%")
        vwap60  = tech.get("vwap60")
        pv60    = tech.get("price_vs_vwap60")
        vwap120 = tech.get("vwap120")
        pv120   = tech.get("price_vs_vwap120")
        if vwap60 and pv60 is not None:
            pos = "高于" if pv60 >= 0 else "低于"
            tech_lines.append(f"60日VWAP（近期机构成本参考）：¥{vwap60}，现价{pos}{abs(pv60):.1f}%")
        if vwap120 and pv120 is not None:
            pos = "高于" if pv120 >= 0 else "低于"
            tech_lines.append(f"120日VWAP（中期机构成本参考）：¥{vwap120}，现价{pos}{abs(pv120):.1f}%")

    tech_str = ""
    if tech_lines:
        tech_str = "\n【技术支撑位与机构成本参考】\n" + "\n".join(tech_lines)

    signals_str = "\n".join(signals_lines) + tech_str

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

    # 用户持仓成本段落
    entry_str = ""
    if entry_price and entry_price > 0:
        cur_price = price.get("price") if price else None
        if cur_price:
            pnl_pct = (cur_price - entry_price) / entry_price * 100
            pnl_sign = "浮盈" if pnl_pct >= 0 else "浮亏"
            pnl_color = "赚" if pnl_pct >= 0 else "亏"
            days_str = f"，持有自 {buy_date}" if buy_date else ""
            entry_str = (
                f"\n【用户持仓成本】\n"
                f"买入价：¥{entry_price:.2f}{days_str}\n"
                f"现价：¥{cur_price:.2f}，{pnl_sign} {abs(pnl_pct):.1f}%（即每股{pnl_color}¥{abs(cur_price - entry_price):.2f}）\n"
                f"→ 分析结论必须基于用户实际持仓成本。给出明确建议：是加仓、继续持有、减仓、还是止损？"
            )
            # 同时更新 behavioral_hint（有成本时才有意义做亏损/锚定分析）
            if not is_st:
                if pnl_pct < -15:
                    behavioral_hint = f"用户已亏损{abs(pnl_pct):.1f}%（买入价¥{entry_price:.2f}）。诊断损失厌恶（亏损不甘止损）vs 理性止损的边界——何时该认输？"
                elif pnl_pct > 30:
                    behavioral_hint = f"用户浮盈{pnl_pct:.1f}%（买入价¥{entry_price:.2f}）。诊断处置效应（过早锁定利润）——利润是继续跑还是落袋为安？"
                else:
                    behavioral_hint = f"用户持仓成本¥{entry_price:.2f}，{pnl_sign}{abs(pnl_pct):.1f}%。分析以买入价为锚点的锚定效应——正确参考锚是内在价值，不是买入价。"

    user_msg = f"""公司：{name}（{code}）
市场：{market.upper()}{st_warning}
{price_str}
{ff_str}
{profile_str}
{fundamentals_str}
{signals_str}{entry_str}

【新闻分析】
近期新闻（已过滤噪音，按信号重要性排序）：
{news_lines}
{news_summary}

行为金融提示（仅用于 ===DIMS=== 中的「行为金融」字段）：{behavioral_hint}

请按格式输出：先写分析信正文，再输出 ===DIMS=== 结构化维度块。"""

    # 🔍 DEBUG: 打印完整的 user_msg 供诊断
    import os
    if os.environ.get("DEBUG_BUFFETT") == "1":
        print(f"\n{'='*80}")
        print(f"DEBUG: user_msg 内容（共{len(user_msg)}字）")
        print(f"{'='*80}")
        print(user_msg)
        print(f"{'='*80}\n")

    raw = _call_groq(SYSTEM_LETTER, user_msg, max_tokens=900)
    if not raw:
        # LLM 失败时，返回一个最小可行的分析
        # 基于提供的数据进行简单分类
        grade = "C"
        conclusion = "待分析"

        # 检查红旗数据来推断等级
        if signals:
            roe = signals.get("roe", 0)
            pm = signals.get("profit_margin", 0)
            de = signals.get("debt_to_equity", 0)

            red_flags = sum([
                roe < 0.05 or roe < 0,
                pm < 0,
                de > 20,
            ])

            if red_flags >= 2:
                grade = "C"
                conclusion = "卖出"
            elif red_flags == 1:
                grade = "C+"
                conclusion = "减持"
            else:
                grade = "B"
                conclusion = "持有"

        return {
            "conclusion": conclusion,
            "grade": grade,
            "reasoning": f"分析服务暂时不可用。基于可用财务数据的自动判断：{conclusion}",
            "letter_html": f"分析服务暂时不可用。基于可用财务数据的自动判断：{conclusion}",
            "raw_output": "（分析服务暂时不可用）",
            "moat": "—",
            "management": "—",
            "valuation": "—",
            "fund_flow_summary": "—",
            "behavioral": "—",
            "macro_sensitivity": "—",
        }

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
