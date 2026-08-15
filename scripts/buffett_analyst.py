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
from scripts.buffett_utils import (parse_dim, parse_trade_block, split_dims_output,
                                   strip_trade_block, summarize_to_sentence)
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



# shared prompts / Groq client / signal scoring moved to dedicated modules




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
                     locale: str = "zh",
                     serenity_context: str = None) -> dict:
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

    serenity_block_en = f"\n[Serenity supply-chain thesis]\n{serenity_context}" if serenity_context else ""
    serenity_block_zh = f"\n{serenity_context}" if serenity_context else ""

    if locale == "en":
        user_msg = f"""Company: {name} ({code})  Market: {market.upper()}
{price_str}{entry_str}{warn_str}

[Layer 2 quant results — finalised, do not change grade or conclusion]
{quant_str}
{trading_str}{inst_str}{serenity_block_en}

[Recent news — top 3]
{news_lines}
{news_meta}

Write a 150–250 word analysis letter.
- Use Buffett's voice; conclusion paragraph must reference the quant rating (Grade {grade} · {conclusion_display}); do not change the grade or conclusion
- If a Serenity supply-chain thesis is provided, weave in the chokepoint position, key design-wins, and ATM risk before the valuation conclusion
- If trade parameters are provided, output a ===TRADE=== block after the conclusion (fill in only "Position strategy" and "Key triggers"; copy all pre-calculated price lines verbatim)"""
    else:
        user_msg = f"""公司：{name}（{code}）市场：{market.upper()}
{price_str}{entry_str}{warn_str}

【Layer 2 量化结果（已定案，LLM 不得更改评级）】
{quant_str}
{trading_str}{inst_str}{serenity_block_zh}

【近期新闻（前3条重要新闻）】
{news_lines}
{news_meta}

请写150-250字分析信。
- 用巴菲特语气，结论段引用量化评级（{grade}级 · {conclusion}），不要改动评级和结论
- 如果提供了 Serenity 供应链论文，分析中必须涵盖：供应链瓶颈地位、关键设计赢客户、ATM稀释风险，然后再给估值结论
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
            "reasoning":         summarize_to_sentence(reasoning),
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
        "reasoning":         summarize_to_sentence(letter_text),
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
