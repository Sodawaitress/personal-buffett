from datetime import datetime, timezone, timedelta, date as _date

import db
from radar_app.data.stocks import (
    get_analyst_consensus,
    save_analyst_consensus,
    get_industry_signal,
    save_industry_signal,
)

CN_TZ = timezone(timedelta(hours=8))

# ── US-79/89/90 Institution classification ──────────────────────────────────
_PASSIVE_INDEX   = ("Vanguard", "BlackRock", "State Street", "Geode", "Schwab Index",
                    "iShares", "SPDR", "Dimensional Fund", "Northern Trust")
_INVESTMENT_BANK = ("JPMorgan", "Morgan Stanley", "Goldman Sachs", "Wells Fargo",
                    "Citibank", "Bank of America", "Merrill Lynch", "UBS", "Barclays")
_ACTIVE_MANAGER  = ("Fidelity", "T. Rowe Price", "Wellington", "Capital Group",
                    "Dodge & Cox", "American Funds", "Putnam", "MFS Investment",
                    "Invesco", "Franklin Templeton")
_HEDGE_FUND      = ("Renaissance", "Citadel", "Point72", "Two Sigma", "AQR",
                    "Viking", "Pershing Square", "Third Point", "Elliott",
                    "Greenlight", "Baupost", "Bridgewater", "Millennium")

# ── US-90 Activist tiers ──────────────────────────────────────────────────────
_ACTIVIST_T1 = {
    "Elliott":     "Elliott Management（Paul Singer）",
    "Starboard":   "Starboard Value（Jeff Smith）",
    "Third Point": "Third Point（Dan Loeb）",
    "Trian":       "Trian Fund Management（Nelson Peltz）",
    "ValueAct":    "ValueAct Capital",
    "Jana":        "Jana Partners",
}
_ACTIVIST_T2 = {
    "Icahn":           "Carl Icahn",
    "Pershing Square": "Pershing Square（Bill Ackman）",
    "Greenlight":      "Greenlight Capital（David Einhorn）",
}


def _fetch_1a_quote(code, market, log):
    """Layer 1a · 行情层：当前价格/涨跌/成交量。不缓存，每次都拉最新。"""
    log("  [1/4] 爬取价格…")
    try:
        if market == "nz":
            from scripts.nz_fetch import fetch_nz_quote

            q = fetch_nz_quote(code)
            if q.get("price"):
                db.upsert_price(
                    code,
                    q["price"],
                    change_pct=q.get("change_pct"),
                    volume=q.get("amount"),
                )
                log(f"       {q['price']} ({q.get('change_pct',0):+.2f}%)")
        elif market == "cn":
            import requests as req

            pure = code.split(".")[0]
            # SH: 5xx (ETF/LOF), 6xx (stock), 9xx (preferred/B); SZ: everything else
            prefix = "sh" if pure.startswith(("5", "6", "9")) else "sz"
            price_saved = False
            try:
                r = req.get(
                    f"https://hq.sinajs.cn/list={prefix}{pure}",
                    headers={"Referer": "https://finance.sina.com.cn"},
                    timeout=10,
                )
                for line in r.text.strip().splitlines():
                    if '="' not in line:
                        continue
                    fields = line.split('"')[1].split(",")
                    if len(fields) < 10:
                        continue
                    price = float(fields[3]) if fields[3] else 0.0
                    prev = float(fields[2]) if fields[2] else 0.0
                    chg = round((price - prev) / prev * 100, 2) if prev else None
                    amt = float(fields[9]) / 1e8 if fields[9] else None
                    if price:
                        db.upsert_price(code, price, change_pct=chg, volume=amt)
                        log(f"       ¥{price} ({chg:+.2f}%)" if chg else f"       ¥{price}")
                        price_saved = True
            except Exception:
                pass

            # 场外基金：Sina API 无数据时改用 AKShare 净值
            if not price_saved:
                try:
                    import akshare as ak
                    df_nav = ak.fund_open_fund_info_em(
                        symbol=pure, indicator="单位净值走势", period="近1个月"
                    )
                    if not df_nav.empty:
                        row = df_nav.iloc[-1]
                        nav = float(row["单位净值"])
                        chg_nav = float(row["日增长率"]) if row["日增长率"] else None
                        db.upsert_price(code, nav, change_pct=chg_nav)
                        log(f"       NAV ¥{nav} ({chg_nav:+.2f}%)" if chg_nav else f"       NAV ¥{nav}")
                except Exception as e2:
                    log(f"       ⚠️ 净值获取失败: {e2}")
        else:
            import yfinance as yf

            t = yf.Ticker(code)
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev = info.get("previousClose")
            chg = round((price - prev) / prev * 100, 2) if price and prev else None
            mc = info.get("marketCap")
            pe = info.get("trailingPE")
            pb = info.get("priceToBook")
            if price:
                db.upsert_price(code, price, change_pct=chg, market_cap=mc, pe_ratio=pe, pb_ratio=pb)
                log(f"       ${price} ({chg:+.2f}%)" if chg else f"       ${price}")
    except Exception as e:
        log(f"       ⚠️ 价格获取失败: {e}")


def _fetch_1c1_news(code, market, log):
    """Layer 1c1 · 新闻情绪层：爬取近30天新闻并打情绪标签。缓存24h。"""
    log("  [2/4] 爬取新闻…")
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    count = 0
    try:
        if market in ("cn", "hk"):
            import akshare as ak

            try:
                df = ak.stock_news_em(symbol=code.split(".")[0])
                for _, row in df.head(20).iterrows():
                    db.upsert_stock_news(
                        code,
                        str(row.get("新闻标题", ""))[:200],
                        str(row.get("新闻来源", "东方财富")),
                        str(row.get("新闻链接", "")),
                        str(row.get("发布时间", today)),
                        today,
                    )
                    count += 1
            except Exception:
                pass
        else:
            import yfinance as yf

            t = yf.Ticker(code)
            for n in t.news[:15]:
                content = n.get("content") if isinstance(n, dict) and "content" in n else n

                if isinstance(content, dict):
                    title = content.get("title", "")
                    publisher = content.get("provider", {})
                    if isinstance(publisher, dict):
                        publisher = publisher.get("displayName", "")
                    else:
                        publisher = ""

                    link_obj = content.get("clickThroughUrl", {})
                    if isinstance(link_obj, dict):
                        link = link_obj.get("url", "")
                    else:
                        link = ""
                    if not link:
                        link_obj = content.get("canonicalUrl", {})
                        if isinstance(link_obj, dict):
                            link = link_obj.get("url", "")
                else:
                    title = n.get("title", "") if n else ""
                    publisher = n.get("publisher", "") if n else ""
                    link = n.get("link", "") if n else ""

                pub_time = today
                if isinstance(content, dict) and "pubDate" in content:
                    try:
                        pub_time = datetime.fromisoformat(content["pubDate"].replace("Z", "+00:00")).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                    except Exception:
                        pub_time = today
                elif n and n.get("providerPublishTime"):
                    try:
                        pub_time = datetime.fromtimestamp(n.get("providerPublishTime")).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pub_time = today

                if title:
                    db.upsert_stock_news(code, title[:200], publisher, link, pub_time, today)
                    count += 1

        if market not in ("cn", "hk"):
            try:
                import feedparser
                import requests as _req

                stock = db.get_stock(code)
                name_en = (stock or {}).get("name", code)
                query = _req.utils.quote(f"{name_en} {code} stock news {datetime.now(CN_TZ).year}")
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
                feed = feedparser.parse(rss_url)
                added = 0
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")[:200]
                    link = entry.get("link", "")
                    pub = entry.get("published", today)[:10]
                    src = (
                        entry.get("source", {}).get("title", "Google News")
                        if isinstance(entry.get("source"), dict)
                        else "Google News"
                    )
                    if title:
                        db.upsert_stock_news(code, title, src, link, pub, today)
                        count += 1
                        added += 1
                log(f"       +Google News {added} 条")
            except Exception as e:
                log(f"       ⚠️ Google News: {e}")

        log(f"       {count} 条新闻")
    except Exception as e:
        log(f"       ⚠️ 新闻获取失败: {e}")


def _fetch_fund_flow(code, market, log):
    if market != "cn":
        return
    log("  [3/4] 爬取主力资金…")
    try:
        import akshare as ak

        pure = code.split(".")[0]
        df = ak.stock_individual_fund_flow(stock=pure, market="sh" if pure.startswith(("6", "9")) else "sz")
        if df is not None and not df.empty:
            row = df.iloc[-1]
            date = str(row.get("日期", datetime.now(CN_TZ).strftime("%Y-%m-%d")))[:10]
            net = float(row.get("主力净流入-净额", 0)) / 1e8
            ratio = float(row.get("主力净流入-净占比", 0))
            db.upsert_fund_flow(code, date, net, ratio)
            arrow = "↑" if net >= 0 else "↓"
            log(f"       {arrow} 主力净{'+' if net >= 0 else ''}{net:.2f}亿 ({ratio:+.1f}%)")
    except Exception as e:
        log(f"       ⚠️ 资金流向获取失败: {e}")


def _fetch_financials(code, market, log):
    log("  [3.5/4] 爬取财务数据…")
    try:
        if market == "cn":
            from scripts.stock_fetch import fetch_cn_financials

            data = fetch_cn_financials(code)
            if data:
                db.upsert_fundamentals(
                    code,
                    annual=data.get("annual", []),
                    pe_current=data.get("pe_current"),
                    pe_percentile_5y=data.get("pe_percentile_5y"),
                    pb_current=data.get("pb_current"),
                    pb_percentile_5y=data.get("pb_percentile_5y"),
                )
                log(f"       PE={data.get('pe_current','?')}x ({data.get('pe_percentile_5y','?')}%分位)")
        else:
            import yfinance as yf

            ticker = yf.Ticker(code)
            info = ticker.info

            fundamentals = {
                "pe_current": info.get("trailingPE"),
                "pb_current": info.get("priceToBook"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "gross_margin": info.get("grossMargins"),
                "profit_margin": info.get("profitMargins"),
            }

            annual = []
            try:
                fin = ticker.financials
                bs = ticker.balance_sheet
                cf = ticker.cashflow
                # US-116 #3：补存 Piotroski-9 + Altman Z'' 所需字段
                def _bs(name, col):
                    return bs.loc[name, col] if name in bs.index and col in bs.columns else None
                def _cf(name, col):
                    return cf.loc[name, col] if name in cf.index and col in cf.columns else None
                def _fin(name, col):
                    return fin.loc[name, col] if name in fin.index and col in fin.columns else None
                def _yi(v):  # 元 → 亿，None 安全
                    try:
                        return round(float(v) / 1e8, 2) if v is not None and v == v else None
                    except (ValueError, TypeError):
                        return None
                years = list(fin.columns)[:4]
                for col in years:
                    try:
                        net_income = fin.loc["Net Income", col] if "Net Income" in fin.index else None
                        total_rev = fin.loc["Total Revenue", col] if "Total Revenue" in fin.index else None
                        equity = _bs("Stockholders Equity", col)
                        total_assets = _bs("Total Assets", col)
                        cur_assets = _bs("Current Assets", col)
                        cur_liab = _bs("Current Liabilities", col)
                        retained = _bs("Retained Earnings", col)
                        shares = _bs("Share Issued", col) or _bs("Ordinary Shares Number", col)
                        cfo = _cf("Operating Cash Flow", col)
                        ebit = _fin("EBIT", col)
                        if ebit is None:
                            ebit = _fin("Operating Income", col)
                        gross_profit = _fin("Gross Profit", col)

                        roe = (net_income / equity * 100) if net_income and equity and equity > 0 else None
                        npm = (net_income / total_rev * 100) if net_income and total_rev and total_rev > 0 else None
                        dar = ((total_assets - equity) / total_assets * 100) if total_assets and equity and total_assets > 0 else None
                        gm = (gross_profit / total_rev * 100) if gross_profit is not None and total_rev else None

                        annual.append(
                            {
                                "year": str(col.year) if hasattr(col, "year") else str(col)[:4],
                                "roe": round(roe, 2) if roe else None,
                                "net_margin": round(npm, 2) if npm else None,
                                "gross_margin": round(gm, 2) if gm is not None else None,
                                "debt_ratio": round(dar, 2) if dar else None,
                                "revenue": round(total_rev / 1e8, 2) if total_rev else None,
                                "net_profit": round(net_income / 1e8, 2) if net_income else None,
                                # US-116 #3 新字段（亿；shares 为原始股数）
                                "total_assets": _yi(total_assets),
                                "current_assets": _yi(cur_assets),
                                "current_liabilities": _yi(cur_liab),
                                "retained_earnings": _yi(retained),
                                "equity": _yi(equity),
                                "ebit": _yi(ebit),
                                "cfo": _yi(cfo),
                                "shares": float(shares) if shares is not None and shares == shares else None,
                            }
                        )
                    except Exception:
                        pass
                if annual:
                    log(f"       年报数据: {len(annual)} 年")
            except Exception as e:
                log(f"       ⚠️ 年报获取失败: {e}")

            db.upsert_fundamentals(
                code,
                annual=annual,
                pe_current=fundamentals.get("pe_current"),
                pb_current=fundamentals.get("pb_current"),
                signals={k: v for k, v in fundamentals.items() if v is not None},
            )
            pe = fundamentals.get("pe_current")
            pb = fundamentals.get("pb_current")
            log(f"       PE={pe if pe else '?'} PB={pb if pb else '?'}")

            yf_sector = info.get("sector") or info.get("industry")
            if yf_sector:
                stock = db.get_stock(code)
                if stock:
                    db.upsert_stock(code, stock.get("name", code), stock.get("market", market), sector=yf_sector)
                    log(f"       sector: {yf_sector}")
    except Exception as e:
        log(f"       ⚠️ 财务数据获取失败: {e}")


def _fetch_advanced(code, market, log):
    log("  [3.6/4] 拉取高级财务数据…")
    try:
        if market == "cn":
            from scripts.stock_fetch import fetch_cn_advanced

            fundamentals = db.get_fundamentals(code)
            annual = fundamentals.get("annual", []) if fundamentals else []
            adv = fetch_cn_advanced(code, annual=annual)
            db.update_annual_json(code, annual)  # US-116 #3：回写 advanced 补进 annual 的字段
            if adv:
                db.upsert_signals(code, adv)
                parts = []
                if "roic_latest" in adv:
                    parts.append(f"ROIC {adv['roic_latest']}%")
                if adv.get("owner_earnings"):
                    oe = adv["owner_earnings"][0]
                    parts.append(f"OE {oe['oe_bn']}亿")
                if "retained_efficiency" in adv:
                    parts.append(f"留存效率{adv['retained_efficiency']:.2f}")
                log(f"       {' | '.join(parts)}")
        else:
            import yfinance as yf

            ticker = yf.Ticker(code)
            info = ticker.info
            adv = {
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
            }
            db.upsert_signals(code, {k: v for k, v in adv.items() if v is not None})
            log(f"       D/E={adv.get('debt_to_equity','?')} 流动比={adv.get('current_ratio','?')}")
    except Exception as e:
        log(f"       ⚠️ 高级财务失败: {e}")


def _fetch_1c3_technicals(code, market, log):
    log("  [3.7/4] 计算技术支撑位…")
    try:
        if market == "cn":
            from scripts.stock_fetch import fetch_cn_technicals

            tech = fetch_cn_technicals(code)
            if tech:
                db.upsert_signals(code, {"technicals": tech})
                parts = []
                if tech.get("ma250") is not None:
                    parts.append(f"年线¥{tech['ma250']} ({tech.get('price_vs_ma250',0):+.1f}%)")
                if tech.get("vwap60") is not None:
                    parts.append(f"60日VWAP¥{tech['vwap60']} ({tech.get('price_vs_vwap60',0):+.1f}%)")
                log(f"       {' | '.join(parts)}")
            else:
                log("       ⚠️ 无数据")
        else:
            import yfinance as yf

            ticker = yf.Ticker(code)
            info = ticker.info

            current_price = info.get("currentPrice")
            fifty_two_week_low = info.get("fiftyTwoWeekLow")
            fifty_two_week_high = info.get("fiftyTwoWeekHigh")

            if current_price and fifty_two_week_low and fifty_two_week_high:
                pos = (current_price - fifty_two_week_low) / (fifty_two_week_high - fifty_two_week_low) * 100
                log(
                    f"       52周价格区间: {fifty_two_week_low:.2f} - {fifty_two_week_high:.2f} (当前位置 {pos:.0f}%)"
                )
                db.upsert_signals(
                    code,
                    {
                        "week_52_low": fifty_two_week_low,
                        "week_52_high": fifty_two_week_high,
                        "price_position": pos,
                    },
                )
    except Exception as e:
        log(f"       ⚠️ 技术支撑位失败: {e}")


def _fetch_signals(code, market, log):
    if market != "cn":
        log("  [3.8/4] 跳过（仅A股支持投行信号）")
        return
    log("  [3.8/4] 爬取投行信号…")
    try:
        from scripts.stock_fetch import fetch_cn_signals

        fundamentals = db.get_fundamentals(code)
        annual = fundamentals.get("annual", []) if fundamentals else []
        signals = fetch_cn_signals(code, annual=annual)
        if signals:
            db.upsert_signals(code, signals)
            parts = []
            if "pledge_ratio" in signals:
                parts.append(f"质押{signals['pledge_ratio']:.1f}%")
            if "margin_direction" in signals:
                parts.append(f"融资{signals['margin_direction']}{abs(signals.get('margin_balance',0))/1e8:.1f}亿")
            if "inst_increased" in signals:
                parts.append(f"机构增{signals['inst_increased']}/减{signals['inst_decreased']}")
            if "fcf_quality_avg" in signals:
                parts.append(f"FCF质量{signals['fcf_quality_avg']:.2f}x")
            log(f"       {' | '.join(parts)}")
    except Exception as e:
        log(f"       ⚠️ 投行信号获取失败: {e}")

    # 计算机构背离分并存入 signals_json
    try:
        from radar_app.data.signal_events import _calc_divergence
        from radar_app.data.market import get_precursor_cache

        fresh = (db.get_fundamentals(code) or {}).get("signals", {})
        precursor = get_precursor_cache(code)
        div = _calc_divergence(precursor, fresh)
        db.upsert_signals(code, {
            "divergence_score":     div["total"],
            "divergence_level":     div["level"],
            "divergence_action":    div["action"],
            "divergence_breakdown": div["breakdown"],
        })
        log(f"       背离分: {div['total']:+d} ({div['level']})")
    except Exception as e:
        log(f"       ⚠️ 背离分计算失败: {e}")


def _fetch_1b_financials(code, market, log):
    _fetch_financials(code, market, log)
    if not _is_st(code):
        _fetch_advanced(code, market, log)
    if market == "cn":
        _fetch_analyst_consensus(code, log)
        _fetch_industry_signal_for_stock(code, market, log)


def _fetch_analyst_consensus(code, log):
    """Fetch analyst EPS consensus (THS, 48h cache). A-share only."""
    existing = get_analyst_consensus(code)
    if existing:
        fetched = existing.get("fetched_at", "")
        try:
            dt = datetime.fromisoformat(str(fetched).replace(" ", "T"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_h < 48:
                log(f"       分析师共识缓存有效（{age_h:.0f}h前）")
                return
        except Exception:
            pass
    try:
        from scripts.fetch_analyst_consensus import fetch_analyst_consensus as _fetch_ac
        data = _fetch_ac(code)
        if data:
            save_analyst_consensus(code, data)
            cnt = data.get("institution_count", 0)
            forecasts = data.get("forecasts", [])
            eps_info = f"EPS{forecasts[0]['year']}均={forecasts[0]['eps_avg']}" if forecasts else "无预测"
            log(f"       👥 {cnt}家机构 {eps_info}")
        else:
            log("       ⚠️ 分析师共识：无数据")
    except Exception as e:
        log(f"       ⚠️ 分析师共识失败: {e}")


def _fetch_industry_signal_for_stock(code, market, log):
    """Fetch industry signal (24h cache) based on company_type from stock_meta."""
    if market != "cn":
        return
    try:
        meta = db.get_stock_meta(code) or {}
        company_type = meta.get("company_type")
        if not company_type:
            return
        from scripts.industry_signals import get_industry_key, fetch_industry_signal, fetch_cycle_commodity_signal
        industry_key = get_industry_key(company_type)
        if not industry_key:
            return
        existing = get_industry_signal(industry_key)
        if existing:
            fetched = existing.get("fetched_at", "")
            try:
                dt = datetime.fromisoformat(str(fetched).replace(" ", "T"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                if age_h < 24:
                    log(f"       行业信号缓存有效（{age_h:.0f}h前，{company_type}）")
                    return
            except Exception:
                pass
        if company_type == "cycle_commodity":
            data = fetch_cycle_commodity_signal()
        else:
            data = fetch_industry_signal(company_type)
        if data:
            save_industry_signal(industry_key, data)
            change = data.get("change_30d", 0)
            signal = data.get("signal", "")
            log(f"       🏭 行业信号 {data.get('label','')} {change:+.1f}% ({signal})")
        else:
            log(f"       ⚠️ 行业信号：{company_type} 无数据")
    except Exception as e:
        log(f"       ⚠️ 行业信号失败: {e}")


def _fetch_north_bound(market, log):
    if market != "cn":
        return
    nb = db.get_north_bound()
    if nb:
        fetched = nb.get("fetched_at", "")
        try:
            dt = datetime.fromisoformat(fetched).replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_h < 24:
                log(f"       北向资金缓存有效（{age_h:.1f}h前）")
                return
        except Exception:
            pass
    try:
        from scripts.stock_fetch import fetch_north_bound

        data = fetch_north_bound()
        if data:
            db.save_north_bound(data)
            sign = "📈" if data.get("total_net", 0) >= 0 else "📉"
            log(f"       {sign} 北向净流入 {data.get('total_net', 0):+.2f}亿")
        else:
            log("       ⚠️ 北向资金无数据")
    except Exception as e:
        log(f"       ⚠️ 北向资金获取失败: {e}")


def _fetch_us_institutional(code, market, log):
    """US-79 · Institutional holder snapshot via yfinance (non-CN markets). 48h cache."""
    from datetime import datetime as _dt2

    # 48h cache: skip if inst_us was fetched within the last 48 hours
    try:
        existing_signals = db.get_fundamentals(code).get("signals", {})
        cached = existing_signals.get("inst_us", {})
        ts_str = cached.get("_fetched_at")
        if ts_str:
            age_h = (_dt2.utcnow() - _dt2.fromisoformat(ts_str)).total_seconds() / 3600
            if age_h < 48:
                log(f"  [3.9a/4] 机构持仓缓存有效（{age_h:.0f}h）")
                return
    except Exception:
        pass

    log("  [3.9a/4] 机构持仓（yfinance）…")
    try:
        import yfinance as yf

        ticker = yf.Ticker(code)
        info = ticker.info

        # Major holder percentages
        inst_pct = inst_count = insider_pct = None
        try:
            mh = ticker.major_holders
            if mh is not None and not mh.empty:
                mh_dict = {str(idx): float(val) for idx, val in zip(mh.index, mh.iloc[:, 0])}
                inst_pct    = mh_dict.get("institutionsPercentHeld")
                insider_pct = mh_dict.get("insidersPercentHeld")
                inst_count  = int(mh_dict.get("institutionsCount", 0)) or None
        except Exception:
            pass

        # Short interest
        short_float_pct = None
        sf = info.get("shortPercentOfFloat")
        if sf is not None:
            try:
                short_float_pct = round(float(sf) * 100, 2)
            except (TypeError, ValueError):
                pass

        short_now  = info.get("sharesShort")
        short_prev = info.get("sharesShortPriorMonth")
        short_trend_pct = None
        if short_now and short_prev and short_prev > 0:
            short_trend_pct = round((short_now - short_prev) / short_prev * 100, 2)

        # Classify top holders, compute active-manager net change
        top_holders   = []
        active_changes = []
        try:
            ih = ticker.institutional_holders
            if ih is not None and not ih.empty:
                for _, r in ih.head(15).iterrows():
                    holder  = str(r.get("Holder", "") or "")
                    pct_h   = float(r.get("pctHeld", 0) or 0)
                    pct_chg = float(r.get("pctChange", 0) or 0)

                    htype = "other"
                    for name in _PASSIVE_INDEX:
                        if name.lower() in holder.lower():
                            htype = "passive"; break
                    if htype == "other":
                        for name in _INVESTMENT_BANK:
                            if name.lower() in holder.lower():
                                htype = "bank"; break
                    if htype == "other":
                        for name in _HEDGE_FUND:
                            if name.lower() in holder.lower():
                                htype = "hedge"; break
                    if htype == "other":
                        for name in _ACTIVE_MANAGER:
                            if name.lower() in holder.lower():
                                htype = "active"; break

                    top_holders.append({"name": holder, "type": htype,
                                        "pct": round(pct_h, 4), "change": round(pct_chg, 4)})
                    if htype in ("active", "hedge"):
                        active_changes.append(pct_chg)
        except Exception:
            pass

        active_net_change = round(sum(active_changes), 4) if active_changes else None

        # Analyst upgrades/downgrades (last 90 days)
        top_analyst_net = None
        try:
            from datetime import date as _d2, timedelta as _td2
            ud = ticker.upgrades_downgrades
            if ud is not None and not ud.empty:
                cutoff = _d2.today() - _td2(days=90)
                idx_dates = ud.index.date if hasattr(ud.index, "date") else None
                recent = ud[idx_dates >= cutoff] if idx_dates is not None else ud.head(30)
                acts = recent["Action"].str.lower()
                ups   = int(acts.str.contains(r"\bup\b|upgrade|reit|raise", na=False).sum())
                downs = int(acts.str.contains(r"\bdown\b|downgrade|lower", na=False).sum())
                top_analyst_net = ups - downs
        except Exception:
            pass

        result = {
            "inst_pct":          inst_pct,
            "insider_pct":       insider_pct,
            "inst_count":        inst_count,
            "active_net_change": active_net_change,
            "short_float_pct":   short_float_pct,
            "short_trend_pct":   short_trend_pct,
            "short_ratio":       info.get("shortRatio"),
            "top_analyst_net":   top_analyst_net,
            "top_holders":       top_holders[:10],
            "_fetched_at":       _dt2.utcnow().isoformat(timespec="seconds"),
        }
        db.upsert_signals(code, {"inst_us": result})

        parts = []
        if inst_pct:
            parts.append(f"机构 {inst_pct*100:.1f}%")
        if short_trend_pct is not None:
            parts.append(f"空头{'↑' if short_trend_pct > 0 else '↓'}{abs(short_trend_pct):.1f}%")
        if top_analyst_net is not None:
            parts.append(f"分析师净{'+' if top_analyst_net >= 0 else ''}{top_analyst_net}")
        log(f"       {' | '.join(parts) or '无数据'}")
    except Exception as e:
        log(f"       ⚠️ 机构持仓失败: {e}")


def _fetch_us_insiders(code, market, log):
    """US-89 · Form 4 C-suite cluster buy detection via yfinance."""
    log("  [3.9b/4] 内部人交易（Form 4）…")
    try:
        import yfinance as yf
        from datetime import date as _d2, timedelta as _td2

        ticker = yf.Ticker(code)
        it = ticker.insider_transactions
        if it is None or it.empty:
            db.upsert_signals(code, {"insider_us": {"cluster_buy": False, "buy_count": 0}})
            log("       无内部人交易数据")
            return

        cutoff = _d2.today() - _td2(days=30)
        buyers = []

        for _, row in it.iterrows():
            pos = str(row.get("Position", "") or "")
            if not any(k in pos.upper() for k in (
                "OFFICER", "DIRECTOR", "CEO", "CFO", "COO", "CTO",
                "PRESIDENT", "EVP", "SVP",
            )):
                continue

            txn = str(row.get("Transaction", "") or "")
            txn_lo = txn.lower()
            # Must be an open-market purchase, not an option exercise
            if not any(k in txn_lo for k in ("purchase", "acquisition", "buy")):
                continue

            start_date = row.get("Start Date")
            if start_date is None:
                continue
            try:
                sd = start_date.date() if hasattr(start_date, "date") else _d2.fromisoformat(str(start_date)[:10])
                if sd < cutoff:
                    continue
            except Exception:
                continue

            try:
                value = float(row.get("Value") or 0)
            except (TypeError, ValueError):
                value = 0
            if value < 100_000:
                continue

            try:
                shares = int(row.get("Shares") or 0)
            except (TypeError, ValueError):
                shares = 0

            buyers.append({
                "name":   str(row.get("Insider", "")),
                "role":   pos,
                "value":  int(value),
                "shares": shares,
                "date":   str(sd),
            })

        total_value = sum(b["value"] for b in buyers)
        cluster_buy = len(buyers) >= 2 and total_value >= 500_000

        db.upsert_signals(code, {"insider_us": {
            "cluster_buy":  cluster_buy,
            "buy_count":    len(buyers),
            "total_value":  total_value,
            "buyers":       buyers[:5],
        }})

        if cluster_buy:
            log(f"       🔥 集群买入! {len(buyers)}人 合计${total_value/1e6:.1f}M")
        elif buyers:
            log(f"       {len(buyers)}笔内部人买入 ${total_value/1e3:.0f}K")
        else:
            log("       无显著内部人买入（30天内）")
    except Exception as e:
        log(f"       ⚠️ 内部人交易失败: {e}")


def _fetch_13d_activist(code, market, log):
    """US-90 · SEC EDGAR SC 13D activist filing detection (US only)."""
    if market != "us":
        return
    log("  [3.9c/4] 激进投资人 13D 侦测…")
    try:
        import requests as _req
        from datetime import date as _d2, timedelta as _td2

        sym = code.split(".")[0]
        start = (_d2.today() - _td2(days=90)).isoformat()
        today = _d2.today().isoformat()

        url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q=%22{sym}%22"
            f"&forms=SC%2013D"
            f"&dateRange=custom&startdt={start}&enddt={today}"
        )
        headers = {"User-Agent": "StockRadarCodex radar@stockradar.example.com"}
        resp = _req.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        hits = (resp.json().get("hits") or {}).get("hits") or []

        found = None
        for hit in hits:
            src = hit.get("_source", {})
            # entity_name = filer; also check display_names array
            names_to_check = [str(src.get("entity_name", "") or "")]
            dn = src.get("display_names") or []
            names_to_check += [str(n) for n in dn]
            combined = " ".join(names_to_check)

            tier = full_name = None
            for key, fname in _ACTIVIST_T1.items():
                if key.lower() in combined.lower():
                    tier = "T1"; full_name = fname; break
            if tier is None:
                for key, fname in _ACTIVIST_T2.items():
                    if key.lower() in combined.lower():
                        tier = "T2"; full_name = fname; break

            if tier:
                filed = str(src.get("file_date", "") or src.get("period_of_report", ""))[:10]
                found = {"found": True, "tier": tier, "name": full_name,
                         "filed_date": filed, "entity": names_to_check[0]}
                break

        result = found or {"found": False}
        db.upsert_signals(code, {"activist_13d": result})

        if found:
            log(f"       🚨 {found['tier']} 激进投资人: {found['name']} ({found['filed_date']})")
        else:
            log("       无激进投资人 13D 申报（近90天）")
    except Exception as e:
        log(f"       ⚠️ EDGAR 13D 查询失败: {e}")


def _fetch_1c2_capital(code, market, log):
    _fetch_north_bound(market, log)
    _fetch_fund_flow(code, market, log)
    if not _is_st(code):
        _fetch_signals(code, market, log)
    if market in ("us", "hk", "au", "nz", "kr"):
        _fetch_us_institutional(code, market, log)
        _fetch_us_insiders(code, market, log)
        _fetch_13d_activist(code, market, log)


def _is_st(code: str) -> bool:
    pure = code.split(".")[0]
    try:
        stock = db.get_stock(code)
        name = (stock or {}).get("name", "")
        return "ST" in name.upper()
    except Exception:
        return False
