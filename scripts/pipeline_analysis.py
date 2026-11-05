import json as _json
from datetime import datetime, timezone, timedelta

import db

CN_TZ = timezone(timedelta(hours=8))
_MARKET_CURRENCY = {"cn": "¥", "us": "$", "hk": "HK$", "nz": "NZ$", "kr": "₩", "au": "A$"}


def _validate_signals(code: str, fundamentals: dict) -> list:
    warnings = []
    if not fundamentals:
        return warnings

    pe = fundamentals.get("pe_current")
    pb = fundamentals.get("pb_current")

    if pe is None:
        warnings.append("PE数据缺失，无法进行市盈率估值，改用PB或其他指标")
        db.log_data_quality(code, "pe_ratio", None, "missing", "PE为NULL")
    elif pe < 0:
        warnings.append(f"PE为负（{pe:.1f}x），公司当前亏损，PE无估值意义")
        db.log_data_quality(code, "pe_ratio", pe, "outlier", "PE<0，亏损状态")
    elif pe > 150:
        warnings.append(f"PE异常高（{pe:.1f}x），通常为利润骤降或数据错误，不纳入PE估值判断，改用PB")
        db.log_data_quality(code, "pe_ratio", pe, "outlier", f"PE={pe:.1f}x >150")

    if pb is not None and pb > 30:
        warnings.append(f"PB异常高（{pb:.1f}x），估值溢价极大，需有护城河支撑")
        db.log_data_quality(code, "pb_ratio", pb, "outlier", f"PB={pb:.1f}x >30")

    try:
        annual = _json.loads(fundamentals.get("annual_json") or "[]")
        if annual:
            latest_roe = annual[0].get("roe") if annual else None
            if latest_roe is not None and latest_roe > 80:
                warnings.append(f"ROE异常高（{latest_roe:.1f}%），可能存在数据错误，谨慎参考")
                db.log_data_quality(code, "roe", latest_roe, "outlier", f"ROE={latest_roe:.1f}% >80%")
            latest_debt = annual[0].get("debt_ratio") if annual else None
            if latest_debt is not None and latest_debt > 90:
                warnings.append(f"资产负债率极高（{latest_debt:.1f}%），财务风险显著，重点评估偿债能力")
                db.log_data_quality(code, "debt_ratio", latest_debt, "outlier", f"负债率={latest_debt:.1f}% >90%")
            latest_margin = annual[0].get("net_margin") if annual else None
            if latest_margin is not None and latest_margin < -50:
                warnings.append(f"净利率深度亏损（{latest_margin:.1f}%），重点关注现金流而非利润")
                db.log_data_quality(code, "net_margin", latest_margin, "outlier", f"净利率={latest_margin:.1f}% <-50%")
    except Exception:
        pass

    return warnings


def _analyze_earnings_quality(annual: list) -> list:
    flags = []
    if not annual or len(annual) < 2:
        return flags

    def _f(s):
        try:
            return float(str(s).replace("%", "").replace("亿", "").strip())
        except Exception:
            return None

    latest = annual[0]
    prev = annual[1]

    growth = _f(latest.get("profit_growth"))
    margin_now = _f(latest.get("net_margin"))
    margin_old = _f(prev.get("net_margin"))
    rev_now = _f(latest.get("revenue"))
    rev_old = _f(prev.get("revenue"))
    roe_vals = [_f(y.get("roe")) for y in annual[:5]]
    roe_vals = [v for v in roe_vals if v is not None]

    if growth is not None and growth > 200:
        flags.append(
            f"【利润质量⚠️】净利润增速{growth:.0f}%属极端值，通常为上年亏损/极低基数所致，"
            f"增速数字本身无参考价值。分析时必须改用利润绝对值，不得将此增速解读为业务加速增长。"
        )
    elif growth is not None and growth > 50 and rev_now and rev_old and rev_old > 0:
        rev_growth = (rev_now - rev_old) / abs(rev_old) * 100
        if growth > rev_growth * 2.5 and growth - rev_growth > 40:
            flags.append(
                f"【利润质量⚠️】净利润增速{growth:.0f}%，但营收仅增{rev_growth:.0f}%，"
                f"差值{growth - rev_growth:.0f}pp。利润增速大幅超过营收，"
                f"高度疑似含一次性收益（资产出售/政府补贴/汇兑/减值冲回等）。"
                f"分析时必须注明此利润可持续性存疑，不得将其当作竞争优势证据。"
            )

    if margin_now is not None and margin_old is not None:
        jump = margin_now - margin_old
        if jump > 10:
            flags.append(
                f"【利润质量⚠️】净利率从{margin_old:.1f}%跳升至{margin_now:.1f}%（+{jump:.1f}pp），"
                f"主营业务毛利改善极少达到此幅度，请核实是否含一次性收益，不得将此净利率改善归因于竞争力提升。"
            )

    if len(roe_vals) >= 4:
        declining = roe_vals[3] >= roe_vals[2] >= roe_vals[1]
        rebounded = roe_vals[0] > roe_vals[1] * 1.4
        if declining and rebounded:
            yr_old = annual[3].get("year", "")
            yr_mid = annual[1].get("year", "")
            flags.append(
                f"【ROE趋势⚠️】ROE在{yr_old}-{yr_mid}连续3年下滑"
                f"({roe_vals[3]:.1f}%->{roe_vals[2]:.1f}%->{roe_vals[1]:.1f}%)，"
                f"最新年反弹至{roe_vals[0]:.1f}%。反弹原因需核实是否一次性，不得直接定性为护城河加固。"
            )

    return flags


# US-224：操作参数文字双语。数字逻辑不变，只按语言选文字（US-141 姿势：生成时带 locale）。
# 默认 zh —— pipeline 写进 LLM prompt 的仍是中文，行为不变；只有详情页按读者语言传 en。
_TP_TEXT = {
    "zh": {
        "e1_ma60":    "{cur}{lo:.2f}–{hi:.2f}（季线MA60附近，回调首选入场区）",
        "e2_ma250":   "{cur}{lo:.2f}–{hi:.2f}（年线MA250附近，强支撑区）",
        "stop_ma250": "{cur}{v:.2f}（年线MA250下方8%，跌破则基本面需重评）",
        "pos_above":  "当前价{cur}{p:.2f}高于所有均线（比MA60高{pct:.1f}%），不是理想进场时机，建议等回调",
        "reduce_ma60": "{cur}{lo:.2f}–{hi:.2f}（MA60上方10-25%，可分批减仓）",
        "pos_broken": "当前价{cur}{p:.2f}已跌破止损位{cur}{stop:.2f}（年线MA250下方8%），技术面破位，暂不建议入场",
        "e1_resist":  "{cur}{lo:.2f}–{hi:.2f}（MA60附近，反弹阻力目标）",
        "e2_resist":  "{cur}{lo:.2f}–{hi:.2f}（年线MA250附近，反弹阻力目标）",
        "pos_below_year": "当前价{cur}{p:.2f}低于年线{cur}{ma250:.2f}，需确认基本面是否变化",
        "pos_between": "当前价{cur}{p:.2f}处于MA60({cur}{ma60:.2f})与MA250({cur}{ma250:.2f})之间，可分批介入",
        "e1_w52":     "{cur}{lo:.2f}–{hi:.2f}（52周区间20-35%分位，历史价值区）",
        "e2_w52":     "{cur}{lo:.2f}–{hi:.2f}（52周低点附近，强支撑区）",
        "stop_w52":   "{cur}{v:.2f}（52周低点下方7%，跌破则趋势可能进一步恶化）",
        "pos_w52_high": "当前价{cur}{p:.2f}处于52周区间高位（{pct:.0f}%分位），接近年高{cur}{hi:.2f}，不是理想进场时机",
        "reduce_w52": "{cur}{lo:.2f}–{hi:.2f}（52周85-100%分位，持仓者可分批减仓）",
        "ref_only":   "（当前价远高于此，仅供参考）",
        "pos_w52_vlow": "当前价{cur}{p:.2f}处于52周极低位（{pct:.0f}%分位），已低于历史价值区（{cur}{lo:.2f}–{hi:.2f}），当前即为买入机会",
        "e1_near":    "{cur}{lo:.2f}–{hi:.2f}（现价附近±3%，已低于52周价值区，性价比高）",
        "pos_w52_low": "当前价{cur}{p:.2f}处于52周低位区间（{pct:.0f}%分位），年低{cur}{lo:.2f}，可关注分批建仓机会",
        "pos_w52_mid": "当前价{cur}{p:.2f}处于52周区间中段（{pct:.0f}%分位），年低{cur}{lo:.2f}，年高{cur}{hi:.2f}",
    },
    "en": {
        "e1_ma60":    "{cur}{lo:.2f}–{hi:.2f} (around the 60-day average; first pullback zone)",
        "e2_ma250":   "{cur}{lo:.2f}–{hi:.2f} (around the 250-day average; strong support)",
        "stop_ma250": "{cur}{v:.2f} (8% below the 250-day average; below this, recheck the fundamentals)",
        "pos_above":  "Price {cur}{p:.2f} is above all moving averages ({pct:.1f}% above the 60-day). Not an ideal entry; a pullback would be better",
        "reduce_ma60": "{cur}{lo:.2f}–{hi:.2f} (10–25% above the 60-day average; holders could trim in stages)",
        "pos_broken": "Price {cur}{p:.2f} has fallen below the stop level {cur}{stop:.2f} (8% under the 250-day average). The chart has broken down; not a time to enter",
        "e1_resist":  "{cur}{lo:.2f}–{hi:.2f} (around the 60-day average; resistance on any rebound)",
        "e2_resist":  "{cur}{lo:.2f}–{hi:.2f} (around the 250-day average; resistance on any rebound)",
        "pos_below_year": "Price {cur}{p:.2f} is below the 250-day average ({cur}{ma250:.2f}). Check whether the fundamentals have changed",
        "pos_between": "Price {cur}{p:.2f} is between the 60-day ({cur}{ma60:.2f}) and 250-day ({cur}{ma250:.2f}) averages. Buying in stages is reasonable",
        "e1_w52":     "{cur}{lo:.2f}–{hi:.2f} (20–35% up the 52-week range; historically good value)",
        "e2_w52":     "{cur}{lo:.2f}–{hi:.2f} (near the 52-week low; strong support)",
        "stop_w52":   "{cur}{v:.2f} (7% below the 52-week low; below this the trend may worsen)",
        "pos_w52_high": "Price {cur}{p:.2f} is {pct:.0f}% of the way up its 52-week range, close to the year high of {cur}{hi:.2f}. Not an ideal entry",
        "reduce_w52": "{cur}{lo:.2f}–{hi:.2f} (top 15% of the 52-week range; holders could trim in stages)",
        "ref_only":   " (current price is well above this; for reference only)",
        "pos_w52_vlow": "Price {cur}{p:.2f} is only {pct:.0f}% of the way up its 52-week range, below the historical value zone ({cur}{lo:.2f}–{hi:.2f}). This is a buying opportunity",
        "e1_near":    "{cur}{lo:.2f}–{hi:.2f} (within 3% of today's price; already below the 52-week value zone)",
        "pos_w52_low": "Price {cur}{p:.2f} is {pct:.0f}% of the way up its 52-week range; year low {cur}{lo:.2f}. Worth watching for a staged entry",
        "pos_w52_mid": "Price {cur}{p:.2f} is {pct:.0f}% of the way up its 52-week range; year low {cur}{lo:.2f}, year high {cur}{hi:.2f}",
    },
}


def _compute_trading_params(price: dict, signals: dict, market: str = "cn", locale: str = "zh") -> dict:
    if not price or not signals:
        return {}

    T = _TP_TEXT.get(locale, _TP_TEXT["zh"])
    cur = _MARKET_CURRENCY.get(market, "$")
    if locale == "en" and cur == "$":
        cur = "US$"   # US-224：新西兰读者读 $ = 新西兰元
    tech = signals.get("technicals", {}) if signals else {}
    current = price.get("price")
    if not current:
        return {}

    ma20 = tech.get("ma20")
    ma60 = tech.get("ma60")
    ma250 = tech.get("ma250")

    if ma60 or ma250:
        params = {"current": current}

        if ma60:
            params["entry_1_low"] = round(ma60 * 0.98, 2)
            params["entry_1_high"] = round(ma60 * 1.02, 2)
            params["entry_1_label"] = T["e1_ma60"].format(cur=cur, lo=ma60 * 0.98, hi=ma60 * 1.02)

        if ma250:
            params["entry_2_low"] = round(ma250 * 0.98, 2)
            params["entry_2_high"] = round(ma250 * 1.02, 2)
            params["entry_2_label"] = T["e2_ma250"].format(cur=cur, lo=ma250 * 0.98, hi=ma250 * 1.02)
            params["stop_loss"] = round(ma250 * 0.92, 2)
            params["stop_loss_label"] = T["stop_ma250"].format(cur=cur, v=ma250 * 0.92)

        if ma20 and ma60 and ma250:
            above_all = current > ma20 and current > ma60 and current > ma250
            below_stop = params.get("stop_loss") and current < params["stop_loss"]
            below_year = current < ma250

            if above_all:
                pct_above_ma60 = (current - ma60) / ma60 * 100
                params["position_label"] = T["pos_above"].format(cur=cur, p=current, pct=pct_above_ma60)
                if pct_above_ma60 >= 10:
                    reduce_low = round(ma60 * 1.10, 2)
                    reduce_high = round(ma60 * 1.25, 2)
                    params["reduce_label"] = T["reduce_ma60"].format(cur=cur, lo=reduce_low, hi=reduce_high)
            elif below_stop:
                params["position_label"] = T["pos_broken"].format(cur=cur, p=current, stop=params["stop_loss"])
                if params.get("entry_1_label"):
                    params["entry_1_label"] = T["e1_resist"].format(cur=cur, lo=params["entry_1_low"], hi=params["entry_1_high"])
                if params.get("entry_2_label"):
                    params["entry_2_label"] = T["e2_resist"].format(cur=cur, lo=params["entry_2_low"], hi=params["entry_2_high"])
                params["entry_1_is_resistance"] = True
                params["entry_2_is_resistance"] = True
            elif below_year:
                params["position_label"] = T["pos_below_year"].format(cur=cur, p=current, ma250=ma250)
            else:
                params["position_label"] = T["pos_between"].format(cur=cur, p=current, ma60=ma60, ma250=ma250)

        return params

    w52_low = signals.get("week_52_low")
    w52_high = signals.get("week_52_high")
    if not w52_low or not w52_high or w52_low >= w52_high:
        return {}

    rng = w52_high - w52_low
    pos_pct = (current - w52_low) / rng * 100
    entry_1_low = round(w52_low + rng * 0.20, 2)
    entry_1_high = round(w52_low + rng * 0.35, 2)
    entry_2_low = round(w52_low * 0.97, 2)
    entry_2_high = round(w52_low * 1.03, 2)
    stop_loss = round(w52_low * 0.93, 2)

    params = {
        "current": current,
        "entry_1_low": entry_1_low,
        "entry_1_high": entry_1_high,
        "entry_1_label": T["e1_w52"].format(cur=cur, lo=entry_1_low, hi=entry_1_high),
        "entry_2_low": entry_2_low,
        "entry_2_high": entry_2_high,
        "entry_2_label": T["e2_w52"].format(cur=cur, lo=entry_2_low, hi=entry_2_high),
        "stop_loss": stop_loss,
        "stop_loss_label": T["stop_w52"].format(cur=cur, v=stop_loss),
    }

    if pos_pct >= 80:
        params["position_label"] = T["pos_w52_high"].format(cur=cur, p=current, pct=pos_pct, hi=w52_high)
        reduce_low = round(w52_low + rng * 0.85, 2)
        reduce_high = round(w52_high, 2)
        params["reduce_label"] = T["reduce_w52"].format(cur=cur, lo=reduce_low, hi=reduce_high)
        params["entry_1_label"] += T["ref_only"]
        params["entry_2_label"] += T["ref_only"]
    elif pos_pct <= 20:
        near_low = round(current * 0.97, 2)
        near_high = round(current * 1.03, 2)
        params["position_label"] = T["pos_w52_vlow"].format(cur=cur, p=current, pct=pos_pct, lo=entry_1_low, hi=entry_1_high)
        params["entry_1_low"] = near_low
        params["entry_1_high"] = near_high
        params["entry_1_label"] = T["e1_near"].format(cur=cur, lo=near_low, hi=near_high)
    elif pos_pct <= 25:
        params["position_label"] = T["pos_w52_low"].format(cur=cur, p=current, pct=pos_pct, lo=w52_low)
    else:
        params["position_label"] = T["pos_w52_mid"].format(cur=cur, p=current, pct=pos_pct, lo=w52_low, hi=w52_high)

    return params


_FUND_KEYWORDS_CN = ("ETF联接", "ETF", "指数", "基金", "LOF", "联接A", "联接C", "联接E")
_FUND_KEYWORDS_EN = ("ETF", "Index Fund", " Fund", "Hedged", "Trust Fund")
# 不用交易所后缀判断基金（.NZ/.AX 下有真实公司），依赖 asset_type 字段 + 名称关键词
_FUND_EXCHANGE_SUFFIXES = ()


def _is_fund(stock: dict) -> bool:
    """检测是否为场外基金/ETF，避免用巴菲特框架错误评级。"""
    if not stock:
        return False
    asset_type = stock.get("asset_type") or ""
    if asset_type in ("场外基金", "ETF"):
        return True
    name = stock.get("name") or ""
    code = stock.get("code") or ""
    if any(kw in name for kw in _FUND_KEYWORDS_CN):
        return True
    # 英文基金名称识别（ETF联接/Hedged/Index Fund 等）
    if any(kw in name for kw in _FUND_KEYWORDS_EN):
        return True
    # 交易所后缀识别（TWH.NZ / VAS.AU 等）
    if any(code.upper().endswith(sfx) for sfx in _FUND_EXCHANGE_SUFFIXES):
        return True
    return False


def _run_fund_analysis(code, stock, price, log, user_id=None):
    """基金/ETF 专用评分：使用 FundRater v1，输出 4 维评分 + 基金专属结论。"""
    from scripts.fund_rater import FundRater
    from scripts.fund_fetch import fetch_fund_data

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    name  = (stock or {}).get("name", code)

    # 获取该用户已有的 A 股持仓（用于组合适配评分）
    existing_codes: list = []
    if user_id:
        try:
            with db.get_conn() as c:
                rows = c.execute(
                    "SELECT stock_code FROM user_watchlist WHERE user_id=:uid AND status!='sold'",
                    {"uid": user_id},
                ).fetchall()
                existing_codes = [r["stock_code"] for r in rows if r["stock_code"] != code]
        except Exception:
            pass

    log("       [基金] 获取基金数据…")
    fund_data = fetch_fund_data(code, name, existing_cn_codes=existing_codes)

    # 如果行情层已有价格，补填（比 AKShare 更快更准）
    if price and price.get("price") and not fund_data.nav:
        fund_data.nav = price["price"]
    if price and price.get("change_pct") is not None and fund_data.change_pct is None:
        fund_data.change_pct = price["change_pct"]

    log("       [基金] 运行 FundRater…")
    result = FundRater.rate(fund_data)
    log(f"       [基金] {result['subtype_label']} · {result['score']}/100 · {result['conclusion']}")

    # 把 4 维评分存进 DB（复用 moat/management/valuation 字段 + fund_detail_json）
    import json as _json
    db.save_analysis(
        code=code,
        period="daily",
        analysis_date=today,
        grade=result["grade"],
        conclusion=result["conclusion"],
        reasoning=result["reasoning"],
        moat=f"{result['product_score']}/35",
        management=f"{result['target_score']}/35",
        valuation=f"{result['port_score']}/20",
        behavioral=f"{result['exec_score']}/10",
        fund_flow_summary=result["subtype_label"],
        framework_used="fund_v1",
        quant_score=result["score"],
        quant_components=_json.dumps(
            {"subtype": result["subtype"], "dimensions": result["dimensions"]},
            ensure_ascii=False
        ),
    )


def _run_layer2(code, market, log, user_id=None, locale="zh"):
    from scripts.buffett_analyst import _analyze_news_signals
    from scripts.quantitative_rating import QuantitativeRater

    stock = db.get_stock(code)
    price = db.get_latest_price(code)
    fundamentals = db.get_fundamentals(code) or {}
    news = db.get_stock_news(code, days=7)
    events = db.get_stock_events(code, limit=10)
    meta = db.get_stock_meta(code)
    company_type = (meta or {}).get("company_type")

    # 基金/ETF 不适用股票评分体系，走专用基金分析
    if _is_fund(stock):
        log("       检测到场外基金/ETF，切换至 FundRater v1")
        _run_fund_analysis(code, stock, price, log, user_id=user_id)
        quant_result = {"grade": "C", "score": 0, "conclusion": "基金模式", "reasoning": "", "components": {
            "moat": (0, []), "growth_management": (0, []), "safety": (0, []), "valuation": (0, [])
        }}
        return quant_result, {}, {
            "stock": stock, "price": price, "news": news, "fundamentals": fundamentals,
            "signals": {}, "news_signals": {}, "earnings_flags": [], "data_warnings": [],
            "events": events, "company_type": "fund", "entry_price": None, "buy_date": None,
            "annual": [], "fund_flow": {},
        }

    _annual = []
    try:
        _annual = _json.loads(fundamentals.get("annual_json") or "[]")
    except Exception:
        pass

    _signals = fundamentals.get("signals", {})

    entry_price, buy_date = None, None
    if user_id:
        try:
            with db.get_conn() as c:
                row = c.execute(
                    "SELECT buy_price, buy_date FROM user_watchlist WHERE user_id=:uid AND stock_code=:code",
                    {"uid": user_id, "code": code},
                ).fetchone()
                if row and row["buy_price"]:
                    entry_price = float(row["buy_price"])
                    buy_date = row["buy_date"]
        except Exception:
            pass

    name = (stock or {}).get("name", code)
    news_signals = _analyze_news_signals(news, company_name=name)
    earnings_flags = _analyze_earnings_quality(_annual)

    # 困境/重整股：注入近5日涨跌幅（催化剂耗尽检测）
    if company_type == "distressed":
        try:
            events_recent = db.get_stock_events(code, limit=20)
            restructuring_events = [
                e for e in (events_recent or [])
                if e.get("event_type") in ("restructuring_announced", "restructuring_vote", "restructuring_approved")
            ]
            if restructuring_events and price:
                cur = price.get("price", 0)
                chg = price.get("change_pct")
                # 用当日变化作为近期信号的代理指标（完整5日历史需另建价格表）
                if cur and chg is not None:
                    news_signals["recent_gain_pct"] = round(chg, 2)
                    news_signals["restructuring_event_count"] = len(restructuring_events)
        except Exception:
            pass
    data_warnings = _validate_signals(code, fundamentals)

    _key = news_signals.get("key_signals", [])
    news_for_rating = {
        "high_pos_buyback":     1 if "回购" in _key else 0,
        "mid_pos_dividend":     1 if any(k in _key for k in ("分红", "派息")) else 0,
        "high_neg_resignation": 1 if any(k in _key for k in ("辞职", "离职")) else 0,
        "mid_neg_reduction":    1 if "减持" in _key else 0,
    }

    quant_result = QuantitativeRater().rate_stock(
        code=code,
        name=(stock or {}).get("name", code),
        annual_data=_annual,
        pe_percentile=fundamentals.get("pe_percentile_5y"),
        pb_percentile=fundamentals.get("pb_percentile_5y"),
        price_52week_pct=_signals.get("price_position"),
        news_signals=news_for_rating,
        locale=locale,
        signals=_signals,
        company_type=company_type,
        pe_current=fundamentals.get("pe_current"),
        pb_current=fundamentals.get("pb_current"),
        industry=db.get_stock_industry(code),
    )
    log(f"       量化评级: {quant_result['grade']} {quant_result['score']}/100 · {quant_result['conclusion']}")

    trading_params = _compute_trading_params(price, _signals, market=market)
    if trading_params.get("entry_1_label"):
        log(f"       买入区间1: {trading_params['entry_1_label'][:50]}")

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    _fund_flow_row = db.get_fund_flow(code) if market == "cn" else {}

    # feat_price_momentum: average daily change_pct over last 5 sessions
    _feat_price_momentum = None
    try:
        from radar_app.data.stocks import get_price_history as _get_ph
        _ph = _get_ph(code, days=6)
        _changes = [r.get("change_pct") for r in _ph if r.get("change_pct") is not None]
        if len(_changes) >= 3:
            _feat_price_momentum = round(sum(_changes[:5]) / len(_changes[:5]), 4)
    except Exception:
        pass

    # feat_fear_greed: CNN Fear & Greed index from daily macro snapshot
    _feat_fear_greed = None
    try:
        from radar_app.data.market import get_market_snapshot as _get_snap
        _snap = _get_snap()
        if _snap:
            _fg = (_snap.get("data") or {}).get("fear_greed") or {}
            _fg_score = _fg.get("score") if isinstance(_fg, dict) else None
            if _fg_score is not None:
                _feat_fear_greed = int(_fg_score)
    except Exception:
        pass

    # 兼容两种评级结构：旧版 components={moat,growth_management,valuation}；
    # 新版类型感知 components={quality,value,...}（无 moat）。缺键不再 KeyError。
    _comp = quant_result.get("components", {}) or {}
    def _comp0(key):
        v = _comp.get(key)
        return v[0] if isinstance(v, (list, tuple)) and v else None
    if "moat" in _comp:
        _moat_field = f"{_comp0('moat')}/35"
        _mgmt_field = f"{_comp0('growth_management')}/30"
        _val_field  = f"{_comp0('valuation')}/15"
    else:
        _q = _comp0("quality")
        _moat_field = f"{_q}/100" if _q is not None else "—"
        _mgmt_field = "—"
        _val_field  = str(_comp0("value") or "—")

    db.save_analysis(
        code=code,
        period="daily",
        analysis_date=today,
        grade=quant_result["grade"],
        conclusion=quant_result["conclusion"],
        reasoning=quant_result["reasoning"],
        moat=_moat_field,
        management=_mgmt_field,
        valuation=_val_field,
        quant_score=quant_result["score"],
        quant_components=_json.dumps(quant_result["components"], ensure_ascii=False),
        data_incomplete=quant_result.get("data_incomplete", 0),
        framework_used="quant",
        feat_sentiment_avg=round(news_signals.get("sentiment_avg", 0) or 0, 4),
        feat_fund_flow_net=_fund_flow_row.get("main_net"),
        feat_pe_vs_hist=fundamentals.get("pe_percentile_5y"),
        feat_price_momentum=_feat_price_momentum,
        feat_fear_greed=_feat_fear_greed,
    )

    if trading_params:
        db.upsert_signals(code, {"trading_params": _json.dumps(trading_params, ensure_ascii=False)})

    return quant_result, trading_params, {
        "stock": stock,
        "price": price,
        "news": news,
        "fundamentals": fundamentals,
        "signals": _signals,
        "news_signals": news_signals,
        "earnings_flags": earnings_flags,
        "data_warnings": data_warnings,
        "events": events,
        "company_type": company_type,
        "entry_price": entry_price,
        "buy_date": buy_date,
        "annual": _annual,
        "fund_flow": db.get_fund_flow(code) if market == "cn" else {},
    }


def _run_analysis(code, market, log, user_id=None):
    # Resolve locale once, used by both quantitative rater and LLM narrative
    _user_locale = "zh"
    if user_id:
        try:
            with db.get_conn() as _c:
                _urow = _c.execute("SELECT locale FROM users WHERE id=:uid", {"uid": user_id}).fetchone()
                if _urow:
                    _user_locale = _urow["locale"] or "zh"
        except Exception:
            pass

    log("  [4/4] Layer 2 量化评级…")
    try:
        quant_result, trading_params, ctx = _run_layer2(code, market, log, user_id, locale=_user_locale)
    except Exception as e:
        log(f"       ⚠️ Layer 2 失败: {e}")
        return

    log("  [4/4] Layer 3 LLM narrative…")
    try:
        from scripts.buffett_analyst import analyze_stock_v3
        from scripts.buffett_context import build_serenity_context

        serenity_ctx = build_serenity_context(code, locale=_user_locale)
        if serenity_ctx:
            log("       注入 Serenity 供应链论文")

        result = analyze_stock_v3(
            code=code,
            name=(ctx["stock"] or {}).get("name", code),
            market=market,
            quant_result=quant_result,
            trading_params=trading_params,
            news=ctx["news"],
            news_signals=ctx["news_signals"],
            price=ctx["price"],
            fund_flow=ctx["fund_flow"],
            fundamentals=ctx["fundamentals"],
            events=ctx["events"],
            company_type=ctx["company_type"],
            entry_price=ctx["entry_price"],
            buy_date=ctx["buy_date"],
            data_warnings=ctx["data_warnings"],
            earnings_flags=ctx["earnings_flags"],
            inst_signals=ctx["signals"].get("inst_us") if market != "cn" else None,
            locale=_user_locale,
            serenity_context=serenity_ctx,
        )
        if result:
            today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
            db.save_analysis(code=code, period="daily", analysis_date=today, **result)
            log(f"       LLM叙事完成: {result.get('grade','—')} · {result.get('conclusion','')}")
    except Exception as e:
        log(f"       ⚠️ Layer 3 失败（已有量化评级）: {e}")
