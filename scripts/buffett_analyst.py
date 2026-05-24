"""
股票雷达 · 巴菲特 AI 分析模块
使用 Groq (Llama 3) 免费 API，对每只股票生成结构化巴菲特视角点评
"""

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import html as _html
import time
from datetime import datetime, timezone, timedelta
from scripts.buffett_groq import _call_groq
from scripts.buffett_prompts import (
    FRAMEWORK_MAP, SYSTEM_DAILY, SYSTEM_LETTER, SYSTEM_PERIOD,
    get_framework,
)
from scripts.buffett_signals import _analyze_news_signals, _score_news
from scripts.buffett_context import (
    build_behavioral_context,
    build_events_context,
    build_fundamentals_context,
    build_mini_warning_context,
    build_price_context,
    build_profile_context,
    build_signals_context,
    build_trading_context,
    build_v3_entry_context,
    build_v3_price_context,
    build_warning_context,
)
from scripts.buffett_utils import parse_dim, parse_trade_block, split_dims_output, strip_trade_block
from scripts.config import BUFFETT_PROFILES


def _safe_letter(text: str) -> str:
    """Escape HTML special chars so LLM output is safe for | safe rendering.
    The template replaces \\n with <br>, which still works after escaping."""
    return _html.escape(text or "", quote=False)


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
    import db as _db
    from scripts.config import NOISE_KEYWORDS, POSITIVE_SIGNALS, NEGATIVE_SIGNALS

    # 从传入数据的 code 集合推导股票列表，不再依赖硬编码 WATCHLIST
    all_codes = set(news_by_code) | set(quotes_by_code) | set(fund_flows)
    # 从 DB 获取名称
    name_map = {}
    for code in all_codes:
        try:
            s = _db.get_stock(code)
            name_map[code] = (s or {}).get("name", code)
        except Exception:
            name_map[code] = code

    stocks_summary = []
    for code in sorted(all_codes):
        name = name_map[code]
        stock_news = news_by_code.get(code, [])
        if not stock_news:
            stocks_summary.append(f"**{name}（{code}）**：{period_label}内无实质性新闻")
            continue

        # 过滤噪音
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

# shared prompts / Groq client / signal scoring moved to dedicated modules


def analyze_stock_v2(code: str, name: str, market: str,
                     price: dict, news: list, fund_flow: dict,
                     fundamentals: dict = None, signals: dict = None,
                     entry_price: float = None, buy_date: str = None,
                     data_warnings: list = None, earnings_flags: list = None,
                     trading_params: dict = None, events: list = None,
                     company_type: str = None) -> dict:
    """
    pipeline 调用的新版分析函数。
    返回 dict，可直接传给 db.save_analysis(**result)。
    """
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    # 新闻：先排序过滤，再取前8
    # 新闻量化分析
    sorted_news = _score_news(news)
    news_signals = _analyze_news_signals(news, company_name=name)

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

    price_str = build_price_context(market, price)
    ff_str = ""
    if fund_flow and market == "cn":
        net   = fund_flow.get("main_net", 0)
        ratio = fund_flow.get("main_ratio", 0)
        ff_str = f"主力资金净{'流入' if net>=0 else '流出'} {abs(net):.2f}亿（占比{ratio:+.1f}%）"
    profile_str = build_profile_context(code)
    fundamentals_str = build_fundamentals_context(fundamentals)
    signals_str = build_signals_context(market, signals or {}, price or {})
    st_warning, behavioral_hint, entry_str = build_behavioral_context(
        name=name,
        code=code,
        price=price or {},
        fund_flow=fund_flow or {},
        entry_price=entry_price,
        buy_date=buy_date,
    )
    warnings_str = build_warning_context(data_warnings=data_warnings, earnings_flags=earnings_flags)
    trading_str = build_trading_context(company_type, trading_params, compact=False)
    events_str = build_events_context(events)

    user_msg = f"""公司：{name}（{code}）
市场：{market.upper()}{st_warning}
{warnings_str}{trading_str}{events_str}{price_str}
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

    # US-50 · 框架路由：按 company_type 选 system prompt
    framework_name, system_prompt = FRAMEWORK_MAP.get(
        company_type or "mature_value",
        ("buffett", SYSTEM_LETTER)
    )
    print(f"    框架路由: {company_type or 'mature_value'} → {framework_name}")

    raw = _call_groq(system_prompt, user_msg, max_tokens=900)

    trade_block = parse_trade_block(raw)

    if not raw:
        # LLM 失败时，使用纯数据驱动的定量评级系统
        print(f"    ⚠️ LLM 无响应，切换到定量评级系统...")
        from scripts.quantitative_rating import QuantitativeRater

        rater = QuantitativeRater()

        # 准备数据
        annual_data_list = []
        if fundamentals and "annual" in fundamentals:
            annual_data_list = fundamentals.get("annual", [])

        # 提取百分位数
        pe_percentile = None
        pb_percentile = None
        price_52week_pct = None

        if fundamentals:
            pe_percentile = fundamentals.get("pe_percentile_5y")
            pb_percentile = fundamentals.get("pb_percentile_5y")

        # 52周价格位置：优先用 signals 里的真实值，否则不传（让评级系统用 None 处理）
        _sig = fundamentals.get("signals", {}) if fundamentals else {}
        price_52week_pct = _sig.get("price_position")  # pipeline 里算好的 0-100

        _key = news_signals.get("key_signals", [])
        news_signals_for_rating = {
            "high_pos_buyback":     1 if "回购" in _key else 0,
            "mid_pos_dividend":     1 if any(k in _key for k in ("分红", "派息")) else 0,
            "high_neg_resignation": 1 if any(k in _key for k in ("辞职", "离职")) else 0,
            "mid_neg_reduction":    1 if "减持" in _key else 0,
        }

        # 调用定量评级系统
        try:
            rating_result = rater.rate_stock(
                code=code,
                name=name,
                annual_data=annual_data_list,
                pe_percentile=pe_percentile,
                pb_percentile=pb_percentile,
                price_52week_pct=price_52week_pct,
                news_signals=news_signals_for_rating
            )

            grade = rating_result["grade"]
            conclusion = rating_result["conclusion"]
            reasoning = rating_result["reasoning"]

            # 从维度信息中提取描述
            moat_desc = rating_result["components"]["moat"][1][0] if rating_result["components"]["moat"][1] else "—"
            growth_desc = rating_result["components"]["growth_management"][1][0] if rating_result["components"]["growth_management"][1] else "—"
            valuation_desc = rating_result["components"]["valuation"][1][0] if rating_result["components"]["valuation"][1] else "—"
            safety_desc = rating_result["components"]["safety"][1][0] if rating_result["components"]["safety"][1] else "—"

            # 生成分析信
            letter_html = f"""
【定量化评级分析】
综合得分：{rating_result['score']}/100

护城河：{moat_desc}
增长：{growth_desc}
安全性：{safety_desc}
估值：{valuation_desc}

{reasoning}

评级：{grade} 级，建议{conclusion}
"""

            if rating_result.get("red_flags"):
                letter_html += f"\n⚠️ 风险信号：{rating_result['red_flags'][0]}"

            return {
                "conclusion": conclusion,
                "grade": grade,
                "reasoning": reasoning,
                "letter_html": letter_html,
                "raw_output": f"（定量评级系统 - 分数{rating_result['score']}）",
                "moat": moat_desc,
                "management": growth_desc,
                "valuation": valuation_desc,
                "fund_flow_summary": safety_desc,
                "behavioral": "—",
                "macro_sensitivity": "—",
                "framework_used": framework_name,
            }
        except Exception as e:
            print(f"    ⚠️ 定量评级系统出错: {e}")
            # 最后的防线：基础规则
            grade = "C"
            conclusion = "待分析"
            if signals:
                roe = signals.get("roe", 0)
                pm = signals.get("profit_margin", 0)
                de = signals.get("debt_to_equity", 0)
                if de > 100:  # 百分比格式（如80表示80%），转为小数
                    de = de / 100
                red_flags = sum([roe < 0.05, pm < 0, de > 2.0])
                if red_flags >= 2:
                    grade, conclusion = "C", "卖出"
                elif red_flags == 1:
                    grade, conclusion = "C+", "减持"
                else:
                    grade, conclusion = "B", "持有"

            return {
                "conclusion": conclusion,
                "grade": grade,
                "reasoning": "分析服务异常，基于基础规则判断",
                "letter_html": f"基础判断：{conclusion}",
                "raw_output": "（备用方案）",
                "moat": "—",
                "management": "—",
                "valuation": "—",
                "fund_flow_summary": "—",
                "behavioral": "—",
                "macro_sensitivity": "—",
                "framework_used": framework_name,
            }

    letter_text, dims_text = split_dims_output(raw)

    # 定量评级决定 grade + conclusion，不依赖解析 LLM 格式
    grade, conclusion = "C", "持有"
    try:
        from scripts.quantitative_rating import QuantitativeRater
        annual_data = fundamentals.get("annual", []) if fundamentals else []
        _key2 = news_signals.get("key_signals", [])
        _ns = {
            "high_pos_buyback":     1 if "回购" in _key2 else 0,
            "mid_pos_dividend":     1 if any(k in _key2 for k in ("分红", "派息")) else 0,
            "high_neg_resignation": 1 if any(k in _key2 for k in ("辞职", "离职")) else 0,
            "mid_neg_reduction":    1 if "减持" in _key2 else 0,
        }
        _rating = QuantitativeRater().rate_stock(
            code=code,
            name=name,
            annual_data=annual_data,
            pe_percentile=fundamentals.get("pe_percentile_5y") if fundamentals else None,
            pb_percentile=fundamentals.get("pb_percentile_5y") if fundamentals else None,
            price_52week_pct=None,
            news_signals=_ns,
        )
        grade      = _rating.get("grade", "C")
        conclusion = _rating.get("conclusion", "持有")
    except Exception as e:
        print(f"    ⚠️ 定量评级出错，保留默认 C: {e}")

    dims = {
        "moat": parse_dim("护城河", dims_text),
        "management": parse_dim("管理层", dims_text),
        "valuation": parse_dim("估值", dims_text),
        "fund_flow_summary": parse_dim("资金流向", dims_text),
        "behavioral": parse_dim("行为金融", dims_text),
        "macro_sensitivity": parse_dim("宏观敏感度", dims_text),
    }

    # 卖出/减持结论时，确保行为金融字段包含沉没成本提示
    if conclusion in ("卖出", "减持") and dims.get("behavioral"):
        if "沉没" not in dims["behavioral"] and "成本" not in dims["behavioral"]:
            dims["behavioral"] = "忘记买入成本——今天愿意以此价格买入吗？若答案是否，持有的唯一理由是情绪，不是价值。"

    return {
        "conclusion":       conclusion,
        "grade":            grade,
        "reasoning":        letter_text[:200],
        "letter_html":      _safe_letter(letter_text),
        "raw_output":       raw,
        "framework_used":   framework_name,
        "trade_block":      trade_block,
        **dims,
    }


_MARKET_CURRENCY = {"cn": "¥", "us": "$", "hk": "HK$", "nz": "NZ$", "kr": "₩"}


_CONCLUSION_EN = {
    "买入": "Buy", "持有": "Hold", "观察": "Watch", "减持": "Reduce", "卖出": "Sell",
    "博弈介入": "Speculative Play", "观望等待": "Wait and See", "坚决回避": "Avoid",
    "高风险持有": "High-Risk Hold", "回避": "Avoid",
    "适合定投": "Dollar-Cost Average", "适合一次性买入": "Lump Sum Buy",
    "当前估值偏高建议等待": "Overvalued — Wait", "行业过于集中风险偏高": "High Sector Concentration Risk",
    "基金模式": "Fund Mode",
}


def analyze_stock_v3(code: str, name: str, market: str,
                     quant_result: dict, trading_params: dict,
                     news: list, news_signals: dict,
                     price: dict, fund_flow: dict,
                     fundamentals: dict = None, events: list = None,
                     company_type: str = None,
                     entry_price: float = None, buy_date: str = None,
                     data_warnings: list = None, earnings_flags: list = None,
                     inst_signals: dict = None,
                     locale: str = "zh") -> dict:
    """
    Layer 3: mini-prompt LLM narrative letter.
    Layer 2 has already computed quant_result + trading_params.
    locale="en" switches to English system prompts and output.
    """
    # ── Framework routing ───────────────────────────────
    framework_name, system_prompt = get_framework(company_type, locale)
    print(f"    framework: {company_type or 'mature_value'} → {framework_name} [{locale}]")

    # ── 量化结果摘要（Layer 2 已算好） ────────────────────
    score  = quant_result.get("score", 0)
    grade  = quant_result.get("grade", "C")
    conclusion = quant_result.get("conclusion", "持有")
    components = quant_result.get("components", {})
    reasoning  = quant_result.get("reasoning", "")

    def _comp(key):
        c = components.get(key, [0, [], []])
        sc = c[0] if c else 0
        reasons = c[1] if len(c) > 1 else []
        return sc, reasons[:2]  # 最多取前2条原因

    moat_sc,   moat_reasons   = _comp("moat")
    growth_sc, growth_reasons = _comp("growth_management")
    safety_sc, safety_reasons = _comp("safety")
    val_sc,    val_reasons    = _comp("valuation")

    conclusion_display = _CONCLUSION_EN.get(conclusion, conclusion) if locale == "en" else conclusion
    _na = "No data" if locale == "en" else "数据不足"
    _red = "Red flags" if locale == "en" else "红旗"

    if locale == "en":
        quant_lines = [
            f"Quant score: {score}/100 → Grade {grade} · {conclusion_display}",
            f"Moat {moat_sc}/35: {'; '.join(moat_reasons) or _na}",
            f"Growth/Mgmt {growth_sc}/30: {'; '.join(growth_reasons) or _na}",
            f"Safety {safety_sc}/20: {'; '.join(safety_reasons) or _na}",
            f"Valuation {val_sc}/15: {'; '.join(val_reasons) or _na}",
        ]
    else:
        quant_lines = [
            f"量化评分：{score}/100 → {grade}级 · {conclusion}",
            f"护城河 {moat_sc}/35：{'; '.join(moat_reasons) or _na}",
            f"成长/管理层 {growth_sc}/30：{'; '.join(growth_reasons) or _na}",
            f"安全性 {safety_sc}/20：{'; '.join(safety_reasons) or _na}",
            f"估值 {val_sc}/15：{'; '.join(val_reasons) or _na}",
        ]
    if quant_result.get("red_flags"):
        quant_lines.append(f"⚠️ {_red}: {'; '.join(quant_result['red_flags'][:2])}")
    quant_str = "\n".join(quant_lines)

    price_str = build_v3_price_context(market, price or {})
    trading_str = build_trading_context(company_type, trading_params, compact=True)

    sorted_news = _score_news(news)[:3]
    _no_news = "  No recent news" if locale == "en" else "  暂无近期新闻"
    news_lines = "\n".join(
        f"  • {n.get('title','')[:80]} ({n.get('source','')})"
        for n in sorted_news
    ) or _no_news
    ns = news_signals or {}
    _no_sig = "none" if locale == "en" else "无"
    _news_meta_parts = [
        f"sentiment: {ns.get('sentiment_avg', 0)}" if locale == "en" else f"情绪：{ns.get('sentiment_avg', 0)}",
        f"key signals: {', '.join(ns.get('key_signals', [])) or _no_sig}" if locale == "en" else f"关键信号：{', '.join(ns.get('key_signals', [])) or _no_sig}",
    ]
    if ns.get("entity_mismatches"):
        _news_meta_parts.append(f"⚠️ filtered {len(ns['entity_mismatches'])} mismatched entity news" if locale == "en" else f"⚠️已过滤{len(ns['entity_mismatches'])}条同名关联公司新闻")
    if ns.get("dilution_warning"):
        _news_meta_parts.append(f"dilution warning: {ns['dilution_warning']}" if locale == "en" else f"稀释警告：{ns['dilution_warning']}")
    if ns.get("recent_gain_pct") is not None:
        _news_meta_parts.append(f"recent_gain_pct={ns['recent_gain_pct']}")
    if ns.get("restructuring_event_count"):
        _news_meta_parts.append(f"restructuring_event_count={ns['restructuring_event_count']}")
    news_meta = " | ".join(_news_meta_parts)

    entry_str = build_v3_entry_context(market, price or {}, entry_price=entry_price, buy_date=buy_date)
    warn_str = build_mini_warning_context(data_warnings=data_warnings, earnings_flags=earnings_flags)

    # US-79: institutional signals injection for non-CN markets
    inst_str = ""
    if inst_signals and market != "cn":
        _parts = []
        anc = inst_signals.get("active_net_change")
        if anc is not None:
            _dir = "净增持" if anc >= 0 else "净减持"
            _parts.append(f"主动基金{_dir} {abs(anc)*100:.2f}pp" if locale == "zh" else f"Active funds net {'bought' if anc >= 0 else 'sold'} {abs(anc)*100:.2f}pp")
        sf = inst_signals.get("short_float_pct")
        st = inst_signals.get("short_trend_pct")
        if sf is not None:
            _trend = ""
            if st is not None:
                _trend = f"（{'↑上升' if st > 0 else '↓下降'} {abs(st):.1f}%）" if locale == "zh" else f" ({'rising' if st > 0 else 'falling'} {abs(st):.1f}%)"
            _parts.append(f"做空比例 {sf:.1f}%{_trend}" if locale == "zh" else f"Short float {sf:.1f}%{_trend}")
        tan = inst_signals.get("top_analyst_net")
        if tan is not None:
            _parts.append(f"顶级投行近90天净{'升' if tan >= 0 else '降'}级 {abs(tan)} 次" if locale == "zh" else f"Top analyst net {'upgrades' if tan >= 0 else 'downgrades'}: {abs(tan)}")
        if _parts:
            _label = "【机构信号】" if locale == "zh" else "[Institutional signals]"
            inst_str = f"\n{_label}\n" + "\n".join(f"  {p}" for p in _parts)

    if locale == "en":
        user_msg = f"""Company: {name} ({code})  Market: {market.upper()}
{price_str}{entry_str}{warn_str}

[Layer 2 quant results — finalised, do not change grade or conclusion]
{quant_str}
{trading_str}{inst_str}

[Recent news — top 3]
{news_lines}
{news_meta}

Write a 150–250 word analysis letter.
- Use Buffett's voice; conclusion paragraph must reference the quant rating (Grade {grade} · {conclusion_display}); do not change the grade or conclusion
- If trade parameters are provided, output a ===TRADE=== block after the conclusion (fill in only "Position strategy" and "Key triggers"; copy all pre-calculated price lines verbatim)"""
    else:
        user_msg = f"""公司：{name}（{code}）市场：{market.upper()}
{price_str}{entry_str}{warn_str}

【Layer 2 量化结果（已定案，LLM 不得更改评级）】
{quant_str}
{trading_str}{inst_str}

【近期新闻（前3条重要新闻）】
{news_lines}
{news_meta}

请写150-250字分析信。
- 用巴菲特语气，结论段引用量化评级（{grade}级 · {conclusion}），不要改动评级和结论
- 若有操作参数，结论段后另起一行输出 ===TRADE=== 块（只补「仓位策略」和「关键监控」两行，其余行原样复制预计算数字）"""

    raw = _call_groq(system_prompt, user_msg, max_tokens=500)

    if not raw:
        if locale == "en":
            letter_html = f"Based on quantitative analysis: {reasoning}\n\nRating: Grade {grade}, {conclusion_display}."
            if trading_params and trading_params.get("position_label"):
                letter_html += f"\n\nTrade parameters: {trading_params['position_label']}"
        else:
            letter_html = f"基于量化分析：{reasoning}\n\n评级：{grade}级，{conclusion}。"
            if trading_params and trading_params.get("position_label"):
                letter_html += f"\n\n操作参数：{trading_params['position_label']}"
        return {
            "conclusion":        conclusion,
            "grade":             grade,
            "reasoning":         reasoning[:200],
            "letter_html":       letter_html,
            "raw_output":        "（Layer 2 量化备用）",
            "framework_used":    framework_name,
            "trade_block":       None,
            "moat":              f"{moat_sc}/35",
            "management":        f"{growth_sc}/30",
            "valuation":         f"{val_sc}/15",
            "fund_flow_summary": f"安全性 {safety_sc}/20",
            "behavioral":        "—",
            "macro_sensitivity": "—",
        }

    trade_block = parse_trade_block(raw)
    letter_text = strip_trade_block(raw)

    return {
        "conclusion":        conclusion,
        "grade":             grade,
        "reasoning":         letter_text[:200],
        "letter_html":       _safe_letter(letter_text),
        "raw_output":        raw,
        "framework_used":    framework_name,
        "trade_block":       trade_block,
        "moat":              f"{moat_sc}/35：{'; '.join(moat_reasons) or '—'}",
        "management":        f"{growth_sc}/30：{'; '.join(growth_reasons) or '—'}",
        "valuation":         f"{val_sc}/15：{'; '.join(val_reasons) or '—'}",
        "fund_flow_summary": f"安全性 {safety_sc}/20：{'; '.join(safety_reasons) or '—'}",
        "behavioral":        "—",
        "macro_sensitivity": "—",
    }


def analyze_all(data: dict) -> dict:
    """
    日报：分析所有自选股，返回 {code: analysis_text}。
    Groq 免费版限速 30 RPM，每次请求后等 2 秒。
    """
    import db as _db
    results       = {}
    news_map      = data.get("news", {})
    fund_flow_map = data.get("fund_flow", {})
    quotes_map    = data.get("quotes", {})

    # 从传入数据推导股票列表，不再依赖硬编码 WATCHLIST
    all_codes = set(news_map) | set(quotes_map)
    for code in sorted(all_codes):
        stock_news = news_map.get(code, [])
        if not stock_news:
            continue

        try:
            s = _db.get_stock(code)
            name = (s or {}).get("name", code)
        except Exception:
            name = code

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
