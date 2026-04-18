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


def _compute_trading_params(price: dict, signals: dict, market: str = "cn") -> dict:
    if not price or not signals:
        return {}

    cur = _MARKET_CURRENCY.get(market, "$")
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
            params["entry_1_label"] = f"{cur}{ma60 * 0.98:.2f}–{ma60 * 1.02:.2f}（季线MA60附近，回调首选入场区）"

        if ma250:
            params["entry_2_low"] = round(ma250 * 0.98, 2)
            params["entry_2_high"] = round(ma250 * 1.02, 2)
            params["entry_2_label"] = f"{cur}{ma250 * 0.98:.2f}–{ma250 * 1.02:.2f}（年线MA250附近，强支撑区）"
            params["stop_loss"] = round(ma250 * 0.92, 2)
            params["stop_loss_label"] = f"{cur}{ma250 * 0.92:.2f}（年线MA250下方8%，跌破则基本面需重评）"

        if ma20 and ma60 and ma250:
            above_all = current > ma20 and current > ma60 and current > ma250
            below_stop = params.get("stop_loss") and current < params["stop_loss"]
            below_year = current < ma250

            if above_all:
                pct_above_ma60 = (current - ma60) / ma60 * 100
                params["position_label"] = (
                    f"当前价{cur}{current:.2f}高于所有均线（比MA60高{pct_above_ma60:.1f}%），"
                    f"不是理想进场时机，建议等回调"
                )
                if pct_above_ma60 >= 10:
                    reduce_low = round(ma60 * 1.10, 2)
                    reduce_high = round(ma60 * 1.25, 2)
                    params["reduce_label"] = f"{cur}{reduce_low:.2f}–{reduce_high:.2f}（MA60上方10-25%，可分批减仓）"
            elif below_stop:
                params["position_label"] = (
                    f"当前价{cur}{current:.2f}已跌破止损位{cur}{params['stop_loss']:.2f}（年线MA250下方8%），"
                    f"技术面破位，暂不建议入场"
                )
                if params.get("entry_1_label"):
                    params["entry_1_label"] = f"{cur}{params['entry_1_low']:.2f}–{params['entry_1_high']:.2f}（MA60附近，反弹阻力目标）"
                if params.get("entry_2_label"):
                    params["entry_2_label"] = f"{cur}{params['entry_2_low']:.2f}–{params['entry_2_high']:.2f}（年线MA250附近，反弹阻力目标）"
                params["entry_1_is_resistance"] = True
                params["entry_2_is_resistance"] = True
            elif below_year:
                params["position_label"] = f"当前价{cur}{current:.2f}低于年线{cur}{ma250:.2f}，需确认基本面是否变化"
            else:
                params["position_label"] = (
                    f"当前价{cur}{current:.2f}处于MA60({cur}{ma60:.2f})与MA250({cur}{ma250:.2f})之间，可分批介入"
                )

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
        "entry_1_label": f"{cur}{entry_1_low:.2f}–{entry_1_high:.2f}（52周区间20-35%分位，历史价值区）",
        "entry_2_low": entry_2_low,
        "entry_2_high": entry_2_high,
        "entry_2_label": f"{cur}{entry_2_low:.2f}–{entry_2_high:.2f}（52周低点附近，强支撑区）",
        "stop_loss": stop_loss,
        "stop_loss_label": f"{cur}{stop_loss:.2f}（52周低点下方7%，跌破则趋势可能进一步恶化）",
    }

    if pos_pct >= 80:
        params["position_label"] = (
            f"当前价{cur}{current:.2f}处于52周区间高位（{pos_pct:.0f}%分位），"
            f"接近年高{cur}{w52_high:.2f}，不是理想进场时机"
        )
        reduce_low = round(w52_low + rng * 0.85, 2)
        reduce_high = round(w52_high, 2)
        params["reduce_label"] = f"{cur}{reduce_low:.2f}–{reduce_high:.2f}（52周85-100%分位，持仓者可分批减仓）"
        params["entry_1_label"] += "（当前价远高于此，仅供参考）"
        params["entry_2_label"] += "（当前价远高于此，仅供参考）"
    elif pos_pct <= 20:
        near_low = round(current * 0.97, 2)
        near_high = round(current * 1.03, 2)
        params["position_label"] = (
            f"当前价{cur}{current:.2f}处于52周极低位（{pos_pct:.0f}%分位），"
            f"已低于历史价值区（{cur}{entry_1_low:.2f}–{entry_1_high:.2f}），当前即为买入机会"
        )
        params["entry_1_low"] = near_low
        params["entry_1_high"] = near_high
        params["entry_1_label"] = f"{cur}{near_low:.2f}–{near_high:.2f}（现价附近±3%，已低于52周价值区，性价比高）"
    elif pos_pct <= 25:
        params["position_label"] = (
            f"当前价{cur}{current:.2f}处于52周低位区间（{pos_pct:.0f}%分位），"
            f"年低{cur}{w52_low:.2f}，可关注分批建仓机会"
        )
    else:
        params["position_label"] = (
            f"当前价{cur}{current:.2f}处于52周区间中段（{pos_pct:.0f}%分位），"
            f"年低{cur}{w52_low:.2f}，年高{cur}{w52_high:.2f}"
        )

    return params


def _run_layer2(code, market, log, user_id=None):
    from scripts.buffett_analyst import _analyze_news_signals
    from scripts.quantitative_rating import QuantitativeRater

    stock = db.get_stock(code)
    price = db.get_latest_price(code)
    fundamentals = db.get_fundamentals(code) or {}
    news = db.get_stock_news(code, days=7)
    events = db.get_stock_events(code, limit=10)
    meta = db.get_stock_meta(code)
    company_type = (meta or {}).get("company_type")

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
                    "SELECT buy_price, buy_date FROM user_watchlist WHERE user_id=? AND stock_code=?",
                    (user_id, code),
                ).fetchone()
                if row and row["buy_price"]:
                    entry_price = float(row["buy_price"])
                    buy_date = row["buy_date"]
        except Exception:
            pass

    news_signals = _analyze_news_signals(news)
    earnings_flags = _analyze_earnings_quality(_annual)
    data_warnings = _validate_signals(code, fundamentals)

    news_for_rating = {
        "high_pos_buyback": 1 if "回购" in news_signals.get("summary", "") else 0,
        "mid_pos_dividend": 1 if "分红" in news_signals.get("summary", "") else 0,
        "high_neg_resignation": 1 if "离职" in news_signals.get("summary", "") else 0,
        "mid_neg_reduction": 1 if "减持" in news_signals.get("summary", "") else 0,
    }

    quant_result = QuantitativeRater().rate_stock(
        code=code,
        name=(stock or {}).get("name", code),
        annual_data=_annual,
        pe_percentile=fundamentals.get("pe_percentile_5y"),
        pb_percentile=fundamentals.get("pb_percentile_5y"),
        price_52week_pct=_signals.get("price_position"),
        news_signals=news_for_rating,
    )
    log(f"       量化评级: {quant_result['grade']} {quant_result['score']}/100 · {quant_result['conclusion']}")

    trading_params = _compute_trading_params(price, _signals, market=market)
    if trading_params.get("entry_1_label"):
        log(f"       买入区间1: {trading_params['entry_1_label'][:50]}")

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    _fund_flow_row = db.get_fund_flow(code) if market == "cn" else {}
    db.save_analysis(
        code=code,
        period="daily",
        analysis_date=today,
        grade=quant_result["grade"],
        conclusion=quant_result["conclusion"],
        reasoning=quant_result["reasoning"],
        moat=str(quant_result["components"]["moat"][0]) + "/35",
        management=str(quant_result["components"]["growth_management"][0]) + "/30",
        valuation=str(quant_result["components"]["valuation"][0]) + "/15",
        quant_score=quant_result["score"],
        quant_components=_json.dumps(quant_result["components"], ensure_ascii=False),
        framework_used="quant",
        feat_sentiment_avg=round(news_signals.get("sentiment_avg", 0) or 0, 4),
        feat_fund_flow_net=_fund_flow_row.get("main_net"),
        feat_pe_vs_hist=fundamentals.get("pe_percentile_5y"),
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
    log("  [4/4] Layer 2 量化评级…")
    try:
        quant_result, trading_params, ctx = _run_layer2(code, market, log, user_id)
    except Exception as e:
        log(f"       ⚠️ Layer 2 失败: {e}")
        return

    log("  [4/4] Layer 3 LLM叙事…")
    try:
        from scripts.buffett_analyst import analyze_stock_v3

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
        )
        if result:
            today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
            db.save_analysis(code=code, period="daily", analysis_date=today, **result)
            log(f"       LLM叙事完成: {result.get('grade','—')} · {result.get('conclusion','')}")
    except Exception as e:
        log(f"       ⚠️ Layer 3 失败（已有量化评级）: {e}")
