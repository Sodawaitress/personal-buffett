"""Shared context builders for Buffett analysis prompts."""

from scripts.config import BUFFETT_PROFILES

_CURRENCY_CODES = {"nz": "NZD", "cn": "CNY", "hk": "HKD", "us": "USD"}
_CURRENCY_SYMBOLS = {"cn": "¥", "us": "$", "hk": "HK$", "nz": "NZ$", "kr": "₩"}
_TRADE_COMPANY_TYPES = (None, "mature_value", "growth_tech", "cyclical", "utility", "financial")
_EVENT_LABELS = {
    "st_trigger": "ST触发",
    "st_lifted": "ST解除",
    "restructuring_announced": "重整公告",
    "restructuring_vote": "重整表决",
    "restructuring_approved": "重整批准",
    "rights_issue": "供股/配股",
    "bonus_share": "转增股本",
    "name_change": "公司改名",
    "delist_warning": "退市警示",
    "delist_final": "退市",
    "major_shareholder_change": "大股东变动",
}


def _pct_val(value):
    try:
        return float(str(value).replace("%", "").strip())
    except Exception:
        return None


def build_price_context(market: str, price: dict) -> str:
    if not price:
        return ""
    current = price.get("price")
    change = price.get("change_pct")
    cur = _CURRENCY_CODES.get(market, "USD")
    if current:
        return f"当前价格：{cur} {current:.2f}（{change:+.2f}%）" if change is not None else f"当前价格：{cur} {current:.2f}"
    return ""


def build_profile_context(code: str) -> str:
    profile = BUFFETT_PROFILES.get(code, {})
    lines = []
    if profile.get("grade"):
        lines.append(f"历史评级参考：{profile['grade']}级")
    if profile.get("biz_type"):
        lines.append(f"生意类型：{profile['biz_type']}")
    if profile.get("moat"):
        lines.append(f"护城河：{profile['moat']}")
    if profile.get("roe_5y"):
        lines.append(f"近5年ROE：{profile['roe_5y']}")
    if profile.get("net_margin_trend"):
        lines.append(f"净利率趋势：{profile['net_margin_trend']}")
    if profile.get("key_risk"):
        lines.append(f"核心风险：{profile['key_risk']}")
    return "\n".join(lines)


def build_fundamentals_context(fundamentals: dict) -> str:
    lines = []
    if not fundamentals:
        return ""

    annual = fundamentals.get("annual", [])
    if annual:
        lines.append("近年财务数据（年报）：")
        for row in annual[:5]:
            year = row.get("year", "")
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
                lines.append(f"  {year}: {', '.join(parts)}")

    latest_annual = annual[0] if annual else {}
    latest_roe = _pct_val(latest_annual.get("roe", ""))
    is_loss_making = latest_roe is not None and latest_roe < 0

    pe_now = fundamentals.get("pe_current")
    pe_pct = fundamentals.get("pe_percentile_5y")
    pb_now = fundamentals.get("pb_current")
    pb_pct = fundamentals.get("pb_percentile_5y")

    if is_loss_making:
        lines.append("⚠️ 估值注意：公司当前ROE为负（亏损状态），PE指标无意义，不可用于估值判断。")
        lines.append("  请聚焦于：何时能扭亏、资产负债表能否支撑、管理层是否有可信的转型计划。")
        if pb_now:
            if pb_pct is not None:
                cheap_pb = "偏低" if pb_pct < 30 else ("偏高" if pb_pct > 70 else "历史中位")
                lines.append(f"  PB {pb_now}x（5年历史{pb_pct}%分位，{cheap_pb}）——亏损时PB是主要参考锚")
            else:
                lines.append(f"  PB {pb_now}x（历史数据不足）——亏损时PB是主要参考锚")
    else:
        if pe_now is not None:
            if pe_now > 200:
                lines.append(f"⚠️ PE数据异常：{pe_now}x（极高PE通常为利润骤降或数据错误，不纳入估值判断，请人工核实）")
            elif pe_pct is not None:
                cheap = "偏低估" if pe_pct < 30 else ("偏高估" if pe_pct > 70 else "处于历史中位")
                lines.append(f"估值：PE {pe_now}x（5年历史{pe_pct}%分位，{cheap}）")
            else:
                lines.append(f"估值：PE {pe_now}x（历史数据不足）")
        if pb_now is not None:
            if pb_pct is not None:
                lines.append(f"       PB {pb_now}x（5年历史{pb_pct}%分位）")
            else:
                lines.append(f"       PB {pb_now}x（历史数据不足）")

    return "\n".join(lines)


def build_signals_context(market: str, signals: dict, price: dict) -> str:
    if not signals:
        return ""

    signals_lines = []

    if market != "cn":
        metric_lines = []
        red_flags = []

        roe = signals.get("roe")
        if roe is not None:
            roe_pct = roe * 100
            if roe_pct < 5:
                red_flags.append(f"🚨 ROE 仅 {roe_pct:.2f}%（最新TTM，以此为准，赚钱能力几乎为零）")
            else:
                metric_lines.append(f"  ROE（股东权益回报率）：{roe_pct:.2f}%（最新TTM，以此为准）")

        pm = signals.get("profit_margin")
        if pm is not None:
            pm_pct = pm * 100
            if pm_pct < 0:
                red_flags.append(f"🚨 净利率 {pm_pct:.2f}%（公司在亏损烧钱）")
            else:
                metric_lines.append(f"  净利率：{pm_pct:.2f}%")

        gm = signals.get("gross_margin")
        if gm is not None:
            metric_lines.append(f"  毛利率：{gm * 100:.2f}%")

        de = signals.get("debt_to_equity")
        if de is not None:
            # yfinance 有时返回百分比形式（如 102.63 表示 1.026x），归一化处理
            de_ratio = de / 100 if de > 2.0 else de
            if de_ratio > 2.0:
                red_flags.append(f"🚨 债务比 {de_ratio:.2f}x（极度高杠杆，融资风险高）")
            else:
                metric_lines.append(f"  债务比（D/E）：{de_ratio:.2f}x")

        cr = signals.get("current_ratio")
        if cr is not None:
            metric_lines.append(f"  流动比：{cr:.2f}x")

        pos = signals.get("price_position")
        if pos is not None:
            if pos >= 90:
                red_flags.append(f"📊 52周价格位置 {pos:.1f}%（接近年高，买入风险大）")
            elif pos <= 10:
                metric_lines.append(f"  📊 52周价格位置：{pos:.1f}%（接近年低，买入机会）")
            else:
                metric_lines.append(f"  📊 52周价格位置：{pos:.1f}%")

        if red_flags:
            signals_lines.append("【⚠️ 关键风险指标】")
            signals_lines.extend(red_flags)
        if metric_lines:
            signals_lines.append("【财务指标概览】")
            signals_lines.extend(metric_lines)

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

    roic_trend = signals.get("roic_trend", [])
    if roic_trend:
        roic_str = " → ".join(f"{r['year']}:{r['roic']}%" for r in roic_trend[:5])
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
            roic_peak = max(r["roic"] for r in roic_trend)
            peak_year = next(r["year"] for r in roic_trend if r["roic"] == roic_peak)
            vs_peak = "已接近历史高位" if r_new >= roic_peak * 0.85 else f"仍低于{peak_year}年峰值{roic_peak}%"
            signals_lines.append(f"ROIC（投入资本回报率）：{roic_str}\n  → 趋势判断：{roic_dir}，{vs_peak}")
        else:
            signals_lines.append(f"ROIC：{roic_str}")

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

    re_eff = signals.get("retained_efficiency")
    re_eq = signals.get("retained_equity_change")
    re_np = signals.get("retained_total_profit")
    if re_eff is not None:
        if re_eff >= 1.0:
            re_verdict = "✓ 优秀：每留1元利润，股东权益增加超过1元，管理层在为股东创造价值"
        elif re_eff >= 0.6:
            re_verdict = "○ 良好：每留1元利润，股东权益增加约{:.2f}元（部分通过分红返还股东）".format(re_eff)
        else:
            re_verdict = "✗ 偏低：每留1元利润，股东权益仅增加{:.2f}元，需关注资本配置效率".format(re_eff)
        signals_lines.append(f"留存利润检验（近5年）：{re_verdict}\n  数据：权益增加{re_eq}亿 ÷ 利润合计{re_np}亿 = {re_eff:.2f}")

    inst_inc = signals.get("inst_increased")
    inst_dec = signals.get("inst_decreased")
    inst_total = signals.get("inst_total")
    if inst_total:
        net_sig = "净增持" if (inst_inc or 0) > (inst_dec or 0) else ("净减持" if (inst_dec or 0) > (inst_inc or 0) else "持平")
        signals_lines.append(f"机构持仓：共{inst_total}家，增持{inst_inc}/减持{inst_dec}，{net_sig}")
        top = signals.get("inst_top", [])
        if top:
            top_str = "；".join(f"{t['name']}({t['type']}){'+' if t['change']>=0 else ''}{t['change']:.2f}pp" for t in top[:3])
            signals_lines.append(f"  主要机构：{top_str}")

    fcf = signals.get("fcf_quality_avg")
    if fcf is not None:
        quality = "良好" if fcf >= 0.8 else ("偏低" if fcf >= 0.5 else "差——利润质量存疑")
        signals_lines.append(f"FCF质量（现金流/净利润）：均值{fcf:.2f}x，{quality}")

    tech = signals.get("technicals", {})
    tech_lines = []
    if tech:
        ma_labels = [("ma250", "年线MA250"), ("ma120", "半年线MA120"), ("ma60", "季线MA60"), ("ma20", "月线MA20")]
        for key, label in ma_labels:
            val = tech.get(key)
            pct = tech.get(f"price_vs_{key}")
            if val is not None and pct is not None:
                pos = "高于" if pct >= 0 else "低于"
                tech_lines.append(f"{label}：¥{val}，现价{pos}{abs(pct):.1f}%")
        vwap60 = tech.get("vwap60")
        pv60 = tech.get("price_vs_vwap60")
        vwap120 = tech.get("vwap120")
        pv120 = tech.get("price_vs_vwap120")
        if vwap60 and pv60 is not None:
            pos = "高于" if pv60 >= 0 else "低于"
            tech_lines.append(f"60日VWAP（近期机构成本参考）：¥{vwap60}，现价{pos}{abs(pv60):.1f}%")
        if vwap120 and pv120 is not None:
            pos = "高于" if pv120 >= 0 else "低于"
            tech_lines.append(f"120日VWAP（中期机构成本参考）：¥{vwap120}，现价{pos}{abs(pv120):.1f}%")

    tech_str = ""
    if tech_lines:
        tech_str = "\n【技术支撑位与机构成本参考】\n" + "\n".join(tech_lines)

    return "\n".join(signals_lines) + tech_str


def build_behavioral_context(name: str, code: str, price: dict, fund_flow: dict, entry_price: float = None, buy_date: str = None):
    is_st = "ST" in name.upper() or code.upper().startswith(("ST", "*ST"))
    st_warning = "\n⚠️ 风险警示：该股票为ST/风险警示股，存在退市风险，流动性差，散户占比极高，属于典型彩票型资产。" if is_st else ""

    ff_ratio = fund_flow.get("main_ratio", 0) if fund_flow else 0
    change_pct = price.get("change_pct", 0) if price else 0
    if is_st:
        behavioral_hint = "ST彩票型资产：持有者多为损失厌恶（亏损不甘止损），而非价值判断。诊断这一心理陷阱。"
    elif ff_ratio is not None and ff_ratio < -5:
        behavioral_hint = "主力资金大幅净流出（机构在离场）。从行为经济学角度，散户此时接盘是典型的'博傻'心理，诊断这一现象。"
    elif change_pct is not None and change_pct > 15:
        behavioral_hint = "近期急涨超15%。分析FOMO（错失恐惧）追涨情绪——Kahneman的'系统1思维'在发挥作用。"
    else:
        behavioral_hint = "常规持有状态。分析投资者最常见的锚定效应（以买入价而非内在价值为参考锚）。"

    entry_str = ""
    if entry_price and entry_price > 0:
        current_price = price.get("price") if price else None
        if current_price:
            pnl_pct = (current_price - entry_price) / entry_price * 100
            pnl_sign = "浮盈" if pnl_pct >= 0 else "浮亏"
            pnl_color = "赚" if pnl_pct >= 0 else "亏"
            days_str = f"，持有自 {buy_date}" if buy_date else ""
            entry_str = (
                f"\n【用户持仓成本】\n"
                f"买入价：¥{entry_price:.2f}{days_str}\n"
                f"现价：¥{current_price:.2f}，{pnl_sign} {abs(pnl_pct):.1f}%（即每股{pnl_color}¥{abs(current_price - entry_price):.2f}）\n"
                f"→ 分析结论必须基于用户实际持仓成本。给出明确建议：买入/持有/观察/减持/卖出，结论格式必须是这五个之一。"
            )
            if not is_st:
                if pnl_pct < -15:
                    behavioral_hint = f"用户已亏损{abs(pnl_pct):.1f}%（买入价¥{entry_price:.2f}）。诊断损失厌恶（亏损不甘止损）vs 理性止损的边界——何时该认输？"
                elif pnl_pct > 30:
                    behavioral_hint = f"用户浮盈{pnl_pct:.1f}%（买入价¥{entry_price:.2f}）。诊断处置效应（过早锁定利润）——利润是继续跑还是落袋为安？"
                else:
                    behavioral_hint = f"用户持仓成本¥{entry_price:.2f}，{pnl_sign}{abs(pnl_pct):.1f}%。分析以买入价为锚点的锚定效应——正确参考锚是内在价值，不是买入价。"

    return st_warning, behavioral_hint, entry_str


def build_warning_context(data_warnings: list = None, earnings_flags: list = None) -> str:
    warn_str = ""
    if data_warnings:
        lines = "\n".join(f"  • {w}" for w in data_warnings)
        warn_str = f"\n【⚠️ 数据质量警告 — 分析时必须遵守以下限制】\n{lines}\n"
    if earnings_flags:
        lines = "\n".join(f"  • {f}" for f in earnings_flags)
        warn_str += f"\n【📊 利润质量预判断 — 以下为系统预计算结论，必须在分析中引用，不得忽视】\n{lines}\n"
    return warn_str


def build_trading_context(company_type: str, trading_params: dict, compact: bool = False) -> str:
    if not trading_params or company_type not in _TRADE_COMPANY_TYPES or not trading_params.get("entry_1_label"):
        return ""

    if compact:
        lines = ["【预计算操作参数 — 价格数字已锁定，LLM 只补仓位策略和关键监控】"]
        lines.append(f"  当前位置：{trading_params.get('position_label', '')}")
        if trading_params.get("reduce_label"):
            lines.append(f"  减仓区间：{trading_params['reduce_label']}")
        lines.append(f"  买入区间1：{trading_params.get('entry_1_label', '暂无')}")
        lines.append(f"  买入区间2：{trading_params.get('entry_2_label', '暂无')}")
        lines.append(f"  止损位：{trading_params.get('stop_loss_label', '暂无')}")
    else:
        lines = ["【📌 预计算操作参数 — 数字已由系统计算，LLM 直接引用至 ===TRADE=== 块】"]
        lines.append(f"  当前价格位置：{trading_params.get('position_label', '未知')}")
        if trading_params.get("reduce_label"):
            lines.append(f"  建议减仓区间：{trading_params['reduce_label']}")
        if trading_params.get("entry_1_label"):
            lines.append(f"  建议买入区间1：{trading_params['entry_1_label']}")
        if trading_params.get("entry_2_label"):
            lines.append(f"  建议买入区间2：{trading_params['entry_2_label']}")
        if trading_params.get("stop_loss_label"):
            lines.append(f"  建议止损位：{trading_params['stop_loss_label']}")

    return "\n" + "\n".join(lines) + "\n"


def build_events_context(events: list) -> str:
    if not events:
        return ""
    lines = []
    for event in events[:6]:
        label = _EVENT_LABELS.get(event.get("event_type", ""), event.get("event_type", ""))
        date = event.get("event_date", "未知日期")
        summary = event.get("summary", "")
        lines.append(f"  [{date}] {label}：{summary}")
    return "\n【关键事件时间线】\n" + "\n".join(lines) + "\n"


def build_mini_warning_context(data_warnings: list = None, earnings_flags: list = None) -> str:
    warn_str = ""
    if data_warnings:
        warn_str = "\n⚠️ 数据警告：" + "；".join(data_warnings[:2])
    if earnings_flags:
        warn_str += "\n⚠️ 利润质量：" + earnings_flags[0][:80]
    return warn_str


def build_v3_price_context(market: str, price: dict) -> str:
    cur = _CURRENCY_SYMBOLS.get(market, "$")
    current = (price or {}).get("price")
    change = (price or {}).get("change_pct")
    if current and change is not None:
        return f"当前价：{cur}{current:.2f}（{change:+.2f}%）"
    if current:
        return f"当前价：{cur}{current:.2f}"
    return ""


def build_v3_entry_context(market: str, price: dict, entry_price: float = None, buy_date: str = None) -> str:
    cur = _CURRENCY_SYMBOLS.get(market, "$")
    current = (price or {}).get("price")
    if not entry_price or entry_price <= 0 or not current:
        return ""
    pnl_pct = (current - entry_price) / entry_price * 100
    pnl_sign = "浮盈" if pnl_pct >= 0 else "浮亏"
    days_str = f"，持有自 {buy_date}" if buy_date else ""
    return (
        f"\n【用户持仓】买入价：{cur}{entry_price:.2f}{days_str}"
        f" | 现价 {pnl_sign} {abs(pnl_pct):.1f}%"
        f"\n→ 结论必须考虑持仓成本，给出买入/持有/观察/减持/卖出建议。"
    )
