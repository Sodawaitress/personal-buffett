from datetime import datetime, timezone, timedelta

import db

CN_TZ = timezone(timedelta(hours=8))


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
            prefix = "sh" if pure.startswith(("6", "9")) else "sz"
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
                price = float(fields[3])
                prev = float(fields[2])
                chg = round((price - prev) / prev * 100, 2) if prev else None
                amt = float(fields[9]) / 1e8 if fields[9] else None
                if price:
                    db.upsert_price(code, price, change_pct=chg, volume=amt)
                    log(f"       ¥{price} ({chg:+.2f}%)" if chg else f"       ¥{price}")
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
                query = _req.utils.quote(f"{name_en} {code} stock news 2026")
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
                years = list(fin.columns)[:4]
                for col in years:
                    try:
                        net_income = fin.loc["Net Income", col] if "Net Income" in fin.index else None
                        total_rev = fin.loc["Total Revenue", col] if "Total Revenue" in fin.index else None
                        equity = bs.loc["Stockholders Equity", col] if "Stockholders Equity" in bs.index else None
                        total_assets = bs.loc["Total Assets", col] if "Total Assets" in bs.index else None

                        roe = (net_income / equity * 100) if net_income and equity and equity > 0 else None
                        npm = (net_income / total_rev * 100) if net_income and total_rev and total_rev > 0 else None
                        dar = ((total_assets - equity) / total_assets * 100) if total_assets and equity and total_assets > 0 else None

                        annual.append(
                            {
                                "year": str(col.year) if hasattr(col, "year") else str(col)[:4],
                                "roe": round(roe, 2) if roe else None,
                                "net_margin": round(npm, 2) if npm else None,
                                "debt_ratio": round(dar, 2) if dar else None,
                                "revenue": round(total_rev / 1e8, 2) if total_rev else None,
                                "net_profit": round(net_income / 1e8, 2) if net_income else None,
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


def _fetch_1b_financials(code, market, log):
    _fetch_financials(code, market, log)
    if not _is_st(code):
        _fetch_advanced(code, market, log)


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


def _fetch_1c2_capital(code, market, log):
    _fetch_north_bound(market, log)
    _fetch_fund_flow(code, market, log)
    if not _is_st(code):
        _fetch_signals(code, market, log)


def _is_st(code: str) -> bool:
    pure = code.split(".")[0]
    try:
        stock = db.get_stock(code)
        name = (stock or {}).get("name", "")
        return "ST" in name.upper()
    except Exception:
        return False
