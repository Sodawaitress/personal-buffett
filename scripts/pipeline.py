#!/usr/bin/env python3
"""
私人巴菲特 · 单股分析 Pipeline
添加股票时触发，或定时任务调用。
pipeline_jobs 表追踪状态，前端轮询 /api/job/<id>。
"""
import sys, os, time, threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db
from datetime import datetime, timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))

# ── 步骤函数 ──────────────────────────────────────────

def _fetch_price(code, market, log):
    """Step 1: 爬取当前价格"""
    log("  [1/4] 爬取价格…")
    try:
        if market == "nz":
            from nz_fetch import fetch_nz_quote
            q = fetch_nz_quote(code)
            if q.get("price"):
                db.upsert_price(code, q["price"], change_pct=q.get("change_pct"),
                                volume=q.get("amount"))
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
                prev  = float(fields[2])
                chg   = round((price - prev) / prev * 100, 2) if prev else None
                vol   = float(fields[8]) if fields[8] else None   # 成交量(股)
                amt   = float(fields[9]) / 1e8 if fields[9] else None  # 成交额(亿)
                if price:
                    db.upsert_price(code, price, change_pct=chg, volume=amt)
                    log(f"       ¥{price} ({chg:+.2f}%)" if chg else f"       ¥{price}")
        else:
            import yfinance as yf
            t = yf.Ticker(code)
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev  = info.get("previousClose")
            chg   = round((price-prev)/prev*100, 2) if price and prev else None
            mc    = info.get("marketCap")
            pe    = info.get("trailingPE")
            pb    = info.get("priceToBook")
            if price:
                db.upsert_price(code, price, change_pct=chg,
                                market_cap=mc, pe_ratio=pe, pb_ratio=pb)
                log(f"       ${price} ({chg:+.2f}%)" if chg else f"       ${price}")
    except Exception as e:
        log(f"       ⚠️ 价格获取失败: {e}")


def _fetch_news(code, market, log):
    """Step 2: 爬取近30天新闻"""
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
                # yfinance v1.2.0+ 返回嵌套结构：{'id': ..., 'content': {...}}
                content = n.get("content") if isinstance(n, dict) and "content" in n else n

                # 安全的字段提取（添加 None 检查）
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

                # 时间处理：支持新旧版本
                pub_time = today
                if isinstance(content, dict) and "pubDate" in content:
                    try:
                        pub_time = datetime.fromisoformat(content["pubDate"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                    except:
                        pub_time = today
                elif n and n.get("providerPublishTime"):
                    try:
                        pub_time = datetime.fromtimestamp(n.get("providerPublishTime")).strftime("%Y-%m-%d %H:%M")
                    except:
                        pub_time = today

                # 仅保存有意义的新闻（至少有标题）
                if title:
                    db.upsert_stock_news(
                        code,
                        title[:200],
                        publisher,
                        link,
                        pub_time,
                        today,
                    )
                    count += 1
        # Google News 补充（美股专属，按公司名搜索）
        if market not in ("cn", "hk"):
            try:
                import feedparser, requests as _req
                stock = db.get_stock(code)
                name_en = (stock or {}).get("name", code)
                query = _req.utils.quote(f"{name_en} {code} stock news 2026")
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
                feed = feedparser.parse(rss_url)
                added = 0
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")[:200]
                    link  = entry.get("link", "")
                    pub   = entry.get("published", today)[:10]
                    src   = entry.get("source", {}).get("title", "Google News") if isinstance(entry.get("source"), dict) else "Google News"
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
    """Step 3: A股主力资金（其他市场跳过）"""
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
            net  = float(row.get("主力净流入-净额", 0)) / 1e8
            ratio= float(row.get("主力净流入-净占比", 0))
            db.upsert_fund_flow(code, date, net, ratio)
            arrow = "↑" if net >= 0 else "↓"
            log(f"       {arrow} 主力净{'+' if net>=0 else ''}{net:.2f}亿 ({ratio:+.1f}%)")
    except Exception as e:
        log(f"       ⚠️ 资金流向获取失败: {e}")


def _fetch_financials(code, market, log):
    """Step 3.5: 财务数据（A股/美股/港股/NZ股）"""
    log("  [3.5/4] 爬取财务数据…")
    try:
        if market == "cn":
            # A股财务数据
            from stock_fetch import fetch_cn_financials
            data = fetch_cn_financials(code)
            if data:
                db.upsert_fundamentals(
                    code,
                    annual          = data.get("annual", []),
                    pe_current      = data.get("pe_current"),
                    pe_percentile_5y= data.get("pe_percentile_5y"),
                    pb_current      = data.get("pb_current"),
                    pb_percentile_5y= data.get("pb_percentile_5y"),
                )
                log(f"       PE={data.get('pe_current','?')}x ({data.get('pe_percentile_5y','?')}%分位)")
        else:
            # 美股/港股/NZ股财务数据（yfinance）
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

            # 抓取历史年报数据构建 annual_data
            annual = []
            try:
                fin = ticker.financials
                bs  = ticker.balance_sheet
                years = list(fin.columns)[:4]  # 最近4年
                for col in years:
                    try:
                        net_income   = fin.loc["Net Income", col] if "Net Income" in fin.index else None
                        total_rev    = fin.loc["Total Revenue", col] if "Total Revenue" in fin.index else None
                        equity       = bs.loc["Stockholders Equity", col] if "Stockholders Equity" in bs.index else None
                        total_assets = bs.loc["Total Assets", col] if "Total Assets" in bs.index else None

                        roe = (net_income / equity * 100) if net_income and equity and equity > 0 else None
                        npm = (net_income / total_rev * 100) if net_income and total_rev and total_rev > 0 else None
                        dar = ((total_assets - equity) / total_assets * 100) if total_assets and equity and total_assets > 0 else None

                        annual.append({
                            "year":       str(col.year) if hasattr(col, "year") else str(col)[:4],
                            "roe":        round(roe, 2) if roe else None,
                            "net_margin": round(npm, 2) if npm else None,
                            "debt_ratio": round(dar, 2) if dar else None,
                            "revenue":    round(total_rev / 1e8, 2) if total_rev else None,
                            "net_profit": round(net_income / 1e8, 2) if net_income else None,
                        })
                    except Exception:
                        pass
                if annual:
                    log(f"       年报数据: {len(annual)} 年")
            except Exception as e:
                log(f"       ⚠️ 年报获取失败: {e}")

            # 通过 signals 参数保存其他财务指标
            db.upsert_fundamentals(
                code,
                annual=annual,
                pe_current=fundamentals.get("pe_current"),
                pb_current=fundamentals.get("pb_current"),
                signals={k:v for k,v in fundamentals.items() if v is not None}
            )
            pe = fundamentals.get("pe_current")
            pb = fundamentals.get("pb_current")
            log(f"       PE={pe if pe else '?'} PB={pb if pb else '?'}")

            # 顺手把 sector 存进 stocks 表（供分类器用）
            yf_sector = info.get("sector") or info.get("industry")
            if yf_sector:
                stock = db.get_stock(code)
                if stock:
                    db.upsert_stock(code, stock.get("name", code),
                                    stock.get("market", market), sector=yf_sector)
                    log(f"       sector: {yf_sector}")
    except Exception as e:
        log(f"       ⚠️ 财务数据获取失败: {e}")


def _fetch_advanced(code, market, log):
    """Step 3.6: 高级财务数据（A股用高级算法，其他用yfinance）"""
    log("  [3.6/4] 拉取高级财务数据…")
    try:
        if market == "cn":
            # A股高级数据
            from stock_fetch import fetch_cn_advanced
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
            # 美股/港股/NZ股简化处理
            import yfinance as yf
            ticker = yf.Ticker(code)
            info = ticker.info

            adv = {
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
            }

            db.upsert_signals(code, {k:v for k,v in adv.items() if v is not None})
            log(f"       D/E={adv.get('debt_to_equity','?')} 流动比={adv.get('current_ratio','?')}")
    except Exception as e:
        log(f"       ⚠️ 高级财务失败: {e}")


def _fetch_technicals(code, market, log):
    """Step 3.7: 技术支撑位（A股用均线，其他用yfinance数据）"""
    log("  [3.7/4] 计算技术支撑位…")
    try:
        if market == "cn":
            # A股技术指标
            from stock_fetch import fetch_cn_technicals
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
            # 美股/港股/NZ股：获取近期价格区间
            import yfinance as yf
            ticker = yf.Ticker(code)
            info = ticker.info

            current_price = info.get("currentPrice")
            fifty_two_week_low = info.get("fiftyTwoWeekLow")
            fifty_two_week_high = info.get("fiftyTwoWeekHigh")

            if current_price and fifty_two_week_low and fifty_two_week_high:
                pos = (current_price - fifty_two_week_low) / (fifty_two_week_high - fifty_two_week_low) * 100
                log(f"       52周价格区间: {fifty_two_week_low:.2f} - {fifty_two_week_high:.2f} (当前位置 {pos:.0f}%)")
                db.upsert_signals(code, {
                    "week_52_low": fifty_two_week_low,
                    "week_52_high": fifty_two_week_high,
                    "price_position": pos
                })
    except Exception as e:
        log(f"       ⚠️ 技术支撑位失败: {e}")


def _fetch_signals(code, market, log):
    """Step 3.8: 投行信号（仅A股完整，其他市场跳过）"""
    if market != "cn":
        log("  [3.8/4] 跳过（仅A股支持投行信号）")
        return
    log("  [3.8/4] 爬取投行信号…")
    try:
        from stock_fetch import fetch_cn_signals
        # 从已存的 fundamentals 拿 annual 数据供 FCF 计算
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


def _validate_signals(code: str, fundamentals: dict) -> list:
    """
    US-48：Pipeline 前置数据验证。
    检查财务数据合理性，返回人类可读警告列表注入分析 prompt，并写入 data_quality_log。
    不阻塞 pipeline，只是标注问题。
    """
    warnings = []
    if not fundamentals:
        return warnings

    import json

    pe = fundamentals.get("pe_current")
    pb = fundamentals.get("pb_current")

    # PE 检查
    if pe is None:
        warnings.append("PE数据缺失，无法进行市盈率估值，改用PB或其他指标")
        db.log_data_quality(code, "pe_ratio", None, "missing", "PE为NULL")
    elif pe < 0:
        warnings.append(f"PE为负（{pe:.1f}x），公司当前亏损，PE无估值意义")
        db.log_data_quality(code, "pe_ratio", pe, "outlier", "PE<0，亏损状态")
    elif pe > 150:
        warnings.append(f"PE异常高（{pe:.1f}x），通常为利润骤降或数据错误，不纳入PE估值判断，改用PB")
        db.log_data_quality(code, "pe_ratio", pe, "outlier", f"PE={pe:.1f}x >150")

    # PB 检查
    if pb is not None and pb > 30:
        warnings.append(f"PB异常高（{pb:.1f}x），估值溢价极大，需有护城河支撑")
        db.log_data_quality(code, "pb_ratio", pb, "outlier", f"PB={pb:.1f}x >30")

    # ROE / 财务指标检查（annual_json）
    try:
        annual = json.loads(fundamentals.get("annual_json") or "[]")
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
    """
    预计算利润质量标签，注入 prompt 作为事实，不让 LLM 自己判断。
    防止把低基数暴增、一次性收益当护城河正面信号。
    """
    flags = []
    if not annual or len(annual) < 2:
        return flags

    def _f(s):
        """字符串 → float，失败返回 None"""
        try:
            return float(str(s).replace('%', '').replace('亿', '').strip())
        except Exception:
            return None

    latest = annual[0]
    prev   = annual[1]

    growth     = _f(latest.get('profit_growth'))
    margin_now = _f(latest.get('net_margin'))
    margin_old = _f(prev.get('net_margin'))
    rev_now    = _f(latest.get('revenue'))
    rev_old    = _f(prev.get('revenue'))
    roe_vals   = [_f(y.get('roe')) for y in annual[:5]]
    roe_vals   = [v for v in roe_vals if v is not None]

    # ── 1. 利润增速 > 200%：低基数，增速本身无意义 ──────────
    if growth is not None and growth > 200:
        flags.append(
            f"【利润质量⚠️】净利润增速{growth:.0f}%属极端值，通常为上年亏损/极低基数所致，"
            f"增速数字本身无参考价值。分析时必须改用利润绝对值，不得将此增速解读为业务加速增长。"
        )
    # ── 2. 利润增速 > 50% 且远超营收增速：疑含一次性收益 ────
    elif growth is not None and growth > 50 and rev_now and rev_old and rev_old > 0:
        rev_growth = (rev_now - rev_old) / abs(rev_old) * 100
        if growth > rev_growth * 2.5 and growth - rev_growth > 40:
            flags.append(
                f"【利润质量⚠️】净利润增速{growth:.0f}%，但营收仅增{rev_growth:.0f}%，"
                f"差值{growth - rev_growth:.0f}pp。利润增速大幅超过营收，"
                f"高度疑似含一次性收益（资产出售/政府补贴/汇兑/减值冲回等）。"
                f"分析时必须注明此利润可持续性存疑，不得将其当作竞争优势证据。"
            )

    # ── 3. 净利率单年跳升 > 10pp ────────────────────────────
    if margin_now is not None and margin_old is not None:
        jump = margin_now - margin_old
        if jump > 10:
            flags.append(
                f"【利润质量⚠️】净利率从{margin_old:.1f}%跳升至{margin_now:.1f}%（+{jump:.1f}pp），"
                f"主营业务毛利改善极少达到此幅度，请核实是否含一次性收益，不得将此净利率改善归因于竞争力提升。"
            )

    # ── 4. ROE 连续2年下滑后突然反弹 ───────────────────────
    if len(roe_vals) >= 4:
        # roe_vals[0]=最新, roe_vals[1]=上年, roe_vals[2]=上上年, roe_vals[3]=3年前
        declining = roe_vals[3] >= roe_vals[2] >= roe_vals[1]  # 连续3年下滑
        rebounded = roe_vals[0] > roe_vals[1] * 1.4             # 最新年反弹40%以上
        if declining and rebounded:
            yr_old = annual[3].get("year", "")
            yr_mid = annual[1].get("year", "")
            flags.append(
                f"【ROE趋势\u26a0\ufe0f】ROE在{yr_old}-{yr_mid}连续3年下滑"
                f"({roe_vals[3]:.1f}%->{roe_vals[2]:.1f}%->{roe_vals[1]:.1f}%)，"
                f"最新年反弹至{roe_vals[0]:.1f}%。反弹原因需核实是否一次性，不得直接定性为护城河加固。"
            )

    return flags


_MARKET_CURRENCY = {"cn": "¥", "us": "$", "hk": "HK$", "nz": "NZ$", "kr": "₩"}


def _compute_trading_params(price: dict, signals: dict, market: str = "cn") -> dict:
    """
    预计算操作参数，全部基于数学，不让 LLM 自己算价格。
    A股：基于均线（MA60/MA250）；US/HK/NZ：基于52周高低点简化版。
    返回 dict，注入 prompt 后由 LLM 写进 ===TRADE=== 输出块。
    """
    if not price or not signals:
        return {}

    cur  = _MARKET_CURRENCY.get(market, "$")
    tech    = signals.get('technicals', {}) if signals else {}
    current = price.get('price')
    if not current:
        return {}

    ma20  = tech.get('ma20')
    ma60  = tech.get('ma60')
    ma250 = tech.get('ma250')

    # ── 路径1：A股均线版（有MA60/MA250） ──────────────────
    if ma60 or ma250:
        params = {'current': current}

        if ma60:
            params['entry_1_low']   = round(ma60 * 0.98, 2)
            params['entry_1_high']  = round(ma60 * 1.02, 2)
            params['entry_1_label'] = f"{cur}{ma60 * 0.98:.2f}–{ma60 * 1.02:.2f}（季线MA60附近，回调首选入场区）"

        if ma250:
            params['entry_2_low']   = round(ma250 * 0.98, 2)
            params['entry_2_high']  = round(ma250 * 1.02, 2)
            params['entry_2_label'] = f"{cur}{ma250 * 0.98:.2f}–{ma250 * 1.02:.2f}（年线MA250附近，强支撑区）"
            params['stop_loss']     = round(ma250 * 0.92, 2)
            params['stop_loss_label'] = f"{cur}{ma250 * 0.92:.2f}（年线MA250下方8%，跌破则基本面需重评）"

        if ma20 and ma60 and ma250:
            above_all   = current > ma20 and current > ma60 and current > ma250
            below_stop  = params.get('stop_loss') and current < params['stop_loss']
            below_year  = current < ma250

            if above_all:
                pct_above_ma60 = (current - ma60) / ma60 * 100
                params['position_label'] = (
                    f"当前价{cur}{current:.2f}高于所有均线（比MA60高{pct_above_ma60:.1f}%），"
                    f"不是理想进场时机，建议等回调"
                )
                if pct_above_ma60 >= 10:
                    reduce_low  = round(ma60 * 1.10, 2)
                    reduce_high = round(ma60 * 1.25, 2)
                    params['reduce_label'] = (
                        f"{cur}{reduce_low:.2f}–{reduce_high:.2f}"
                        f"（MA60上方10-25%，可分批减仓）"
                    )
            elif below_stop:
                # 已跌破止损位：均线全部成为上方阻力，买入区间无意义
                params['position_label'] = (
                    f"当前价{cur}{current:.2f}已跌破止损位{cur}{params['stop_loss']:.2f}（年线MA250下方8%），"
                    f"技术面破位，暂不建议入场"
                )
                # 将买入区间改为"反弹目标/阻力"
                if params.get('entry_1_label'):
                    params['entry_1_label'] = f"{cur}{params['entry_1_low']:.2f}–{params['entry_1_high']:.2f}（MA60附近，反弹阻力目标）"
                if params.get('entry_2_label'):
                    params['entry_2_label'] = f"{cur}{params['entry_2_low']:.2f}–{params['entry_2_high']:.2f}（年线MA250附近，反弹阻力目标）"
                # 不显示买入标签，改为下探支撑提示
                params['entry_1_is_resistance'] = True
                params['entry_2_is_resistance'] = True
            elif below_year:
                params['position_label'] = (
                    f"当前价{cur}{current:.2f}低于年线{cur}{ma250:.2f}，需确认基本面是否变化"
                )
            else:
                params['position_label'] = (
                    f"当前价{cur}{current:.2f}处于MA60({cur}{ma60:.2f})与MA250({cur}{ma250:.2f})之间，可分批介入"
                )

        return params

    # ── 路径2：美股/港股/NZ简化版（52周高低点） ──────────
    w52_low  = signals.get('week_52_low')
    w52_high = signals.get('week_52_high')
    if not w52_low or not w52_high or w52_low >= w52_high:
        return {}

    rng = w52_high - w52_low
    pos_pct = (current - w52_low) / rng * 100

    # 价值区间：52周低点上方20-35%（历史估值洼地）
    entry_1_low  = round(w52_low + rng * 0.20, 2)
    entry_1_high = round(w52_low + rng * 0.35, 2)
    # 强支撑区：52周低点 ±3%
    entry_2_low  = round(w52_low * 0.97, 2)
    entry_2_high = round(w52_low * 1.03, 2)
    # 止损：52周低点下方7%
    stop_loss    = round(w52_low * 0.93, 2)

    params = {
        'current': current,
        'entry_1_low':   entry_1_low,
        'entry_1_high':  entry_1_high,
        'entry_1_label': f"{cur}{entry_1_low:.2f}–{entry_1_high:.2f}（52周区间20-35%分位，历史价值区）",
        'entry_2_low':   entry_2_low,
        'entry_2_high':  entry_2_high,
        'entry_2_label': f"{cur}{entry_2_low:.2f}–{entry_2_high:.2f}（52周低点附近，强支撑区）",
        'stop_loss':     stop_loss,
        'stop_loss_label': f"{cur}{stop_loss:.2f}（52周低点下方7%，跌破则趋势可能进一步恶化）",
    }

    if pos_pct >= 80:
        params['position_label'] = (
            f"当前价{cur}{current:.2f}处于52周区间高位（{pos_pct:.0f}%分位），"
            f"接近年高{cur}{w52_high:.2f}，不是理想进场时机"
        )
        # 高位：推算减仓区（年高附近85-100%分位）并隐藏买入区间
        reduce_low  = round(w52_low + rng * 0.85, 2)
        reduce_high = round(w52_high, 2)
        params['reduce_label'] = (
            f"{cur}{reduce_low:.2f}–{reduce_high:.2f}"
            f"（52周85-100%分位，持仓者可分批减仓）"
        )
        # 高位时买入区间仍保留但加注警告
        params['entry_1_label'] += "（当前价远高于此，仅供参考）"
        params['entry_2_label'] += "（当前价远高于此，仅供参考）"
    elif pos_pct <= 20:
        # 价格已低于"价值区"（20-35%分位）→ 当前价就是买入机会，entry_1改为现价附近
        near_low  = round(current * 0.97, 2)
        near_high = round(current * 1.03, 2)
        params['position_label'] = (
            f"当前价{cur}{current:.2f}处于52周极低位（{pos_pct:.0f}%分位），"
            f"已低于历史价值区（{cur}{entry_1_low:.2f}–{entry_1_high:.2f}），当前即为买入机会"
        )
        params['entry_1_low']   = near_low
        params['entry_1_high']  = near_high
        params['entry_1_label'] = (
            f"{cur}{near_low:.2f}–{near_high:.2f}（现价附近±3%，已低于52周价值区，性价比高）"
        )
    elif pos_pct <= 25:
        params['position_label'] = (
            f"当前价{cur}{current:.2f}处于52周低位区间（{pos_pct:.0f}%分位），"
            f"年低{cur}{w52_low:.2f}，可关注分批建仓机会"
        )
    else:
        params['position_label'] = (
            f"当前价{cur}{current:.2f}处于52周区间中段（{pos_pct:.0f}%分位），"
            f"年低{cur}{w52_low:.2f}，年高{cur}{w52_high:.2f}"
        )

    return params


def _run_layer2(code, market, log, user_id=None):
    """
    Layer 2：纯数学，零 LLM token。
    计算 quant 评级 + trading_params，立即存入 DB。
    返回 (quant_result, trading_params, context) 供 Layer 3 使用。
    """
    import json as _json
    from quantitative_rating import QuantitativeRater
    from buffett_analyst import _analyze_news_signals, _analyze_earnings_quality

    stock        = db.get_stock(code)
    price        = db.get_latest_price(code)
    fundamentals = db.get_fundamentals(code) or {}
    news         = db.get_stock_news(code, days=7)
    events       = db.get_stock_events(code, limit=10)
    meta         = db.get_stock_meta(code)
    company_type = (meta or {}).get("company_type")

    _annual = []
    try:
        _annual = _json.loads(fundamentals.get("annual_json") or "[]")
    except Exception:
        pass

    _signals = fundamentals.get("signals", {})

    # 持仓成本
    entry_price, buy_date = None, None
    if user_id:
        try:
            with db.get_conn() as c:
                row = c.execute(
                    "SELECT buy_price, buy_date FROM user_watchlist WHERE user_id=? AND stock_code=?",
                    (user_id, code)
                ).fetchone()
                if row and row["buy_price"]:
                    entry_price = float(row["buy_price"])
                    buy_date    = row["buy_date"]
        except Exception:
            pass

    # ── 量化评级 ──────────────────────────────────────────
    news_signals   = _analyze_news_signals(news)
    earnings_flags = _analyze_earnings_quality(_annual)
    data_warnings  = _validate_signals(code, fundamentals)

    news_for_rating = {
        "high_pos_buyback":      1 if "回购" in news_signals.get("summary", "") else 0,
        "mid_pos_dividend":      1 if "分红" in news_signals.get("summary", "") else 0,
        "high_neg_resignation":  1 if "离职" in news_signals.get("summary", "") else 0,
        "mid_neg_reduction":     1 if "减持" in news_signals.get("summary", "") else 0,
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

    # ── 操作参数 ──────────────────────────────────────────
    trading_params = _compute_trading_params(price, _signals, market=market)
    if trading_params.get("entry_1_label"):
        log(f"       买入区间1: {trading_params['entry_1_label'][:50]}")

    # ── 立即存入 DB（Layer 3 失败也有基础评级）────────────
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
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
    )

    # trading_params 存入 signals，供页面直接读取（不重算）
    if trading_params:
        db.upsert_signals(code, {"trading_params": _json.dumps(trading_params, ensure_ascii=False)})

    return quant_result, trading_params, {
        "stock": stock, "price": price, "news": news,
        "fundamentals": fundamentals, "signals": _signals,
        "news_signals": news_signals, "earnings_flags": earnings_flags,
        "data_warnings": data_warnings, "events": events,
        "company_type": company_type, "entry_price": entry_price,
        "buy_date": buy_date, "annual": _annual,
        "fund_flow": db.get_fund_flow(code) if market == "cn" else {},
    }


def _run_analysis(code, market, log, user_id=None):
    """
    Step 4: Layer 2（量化） + Layer 3（LLM叙事）。
    Layer 2 必跑并立即存 DB；Layer 3 仅补充信件文本。
    """
    log("  [4/4] Layer 2 量化评级…")
    try:
        quant_result, trading_params, ctx = _run_layer2(code, market, log, user_id)
    except Exception as e:
        log(f"       ⚠️ Layer 2 失败: {e}")
        return

    log("  [4/4] Layer 3 LLM叙事…")
    try:
        from buffett_analyst import analyze_stock_v3
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


# ── 超时包装 ──────────────────────────────────────────

STEP_TIMEOUT = 35  # 每步最长等待秒数

def _run_with_timeout(fn, args, label: str, log, timeout: int = STEP_TIMEOUT):
    """在独立线程执行 fn(*args)，超过 timeout 秒则跳过并记录日志。"""
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn, *args)
        try:
            future.result(timeout=timeout)
        except FuturesTimeoutError:
            log(f"  ⏱ {label} 超时（>{timeout}s），跳过")
        except Exception as e:
            log(f"  ⚠️ {label} 失败: {e}")


def _is_st(code: str) -> bool:
    """*ST / ST 股判断——这类股票高级财务API通常质量差或会卡住。"""
    pure = code.split(".")[0]
    try:
        stock = db.get_stock(code)
        name = (stock or {}).get("name", "")
        return "ST" in name.upper()
    except Exception:
        return False


# ── 数据新鲜度检查 ────────────────────────────────────────

# 各步骤缓存有效期（分钟）。0 = 当日存在即视为新鲜（二值判断）。
_CACHE_TTL = {
    "price":        15,       # 15 分钟
    "news":         0,        # 当日有 ≥3 条即跳过
    "fund_flow":    0,        # 当日有数据即跳过
    "fundamentals": 7 * 24 * 60,  # 7 天
    "advanced":     24 * 60,  # 1 天
    "technicals":   24 * 60,  # 1 天
    "signals":      24 * 60,  # 1 天
}


def _data_age_minutes(code: str, step: str) -> float:
    """返回缓存数据的年龄（分钟）。无数据返回 inf。"""
    now_utc = datetime.now(timezone.utc)
    today_cn = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    try:
        with db.get_conn() as c:
            if step == "price":
                count = c.execute(
                    "SELECT COUNT(*) FROM stock_prices WHERE code=? "
                    "AND fetched_at > datetime('now', '-15 minutes')",
                    (code,)
                ).fetchone()[0]
                return 0 if count > 0 else float('inf')
            elif step == "news":
                count = c.execute(
                    "SELECT COUNT(*) FROM stock_news WHERE code=? AND fetched_date=?",
                    (code, today_cn)
                ).fetchone()[0]
                return 0 if count >= 3 else float('inf')
            elif step == "fund_flow":
                row = c.execute(
                    "SELECT date FROM stock_fund_flow WHERE code=? ORDER BY date DESC LIMIT 1",
                    (code,)
                ).fetchone()
                return 0 if (row and row[0] == today_cn) else float('inf')
            elif step in ("fundamentals", "advanced", "technicals", "signals"):
                row = c.execute(
                    "SELECT updated_at FROM stock_fundamentals WHERE code=?",
                    (code,)
                ).fetchone()
                if not row or not row[0]:
                    return float('inf')
                try:
                    dt = datetime.fromisoformat(row[0])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return (now_utc - dt).total_seconds() / 60
                except Exception:
                    return float('inf')
    except Exception:
        pass
    return float('inf')


def _is_stale(code: str, step: str, force: bool) -> bool:
    """True = 需要重新抓取；False = 缓存新鲜，可跳过。"""
    if force:
        return True
    age = _data_age_minutes(code, step)
    return age > _CACHE_TTL[step]


# ── 主 pipeline ────────────────────────────────────────

def run_pipeline(job_id: int, code: str, market: str, user_id: int = None, force: bool = True):
    """
    在后台线程中运行。每步有独立超时，不会因单步卡住拖死整个分析。
    force=True（默认）：全量重爬，忽略缓存。
    force=False：跳过新鲜数据（价格<15min / 新闻当日已有 / 财务<7天 等），
                 适合 admin rerun-all 批量运行节省时间。
    """
    logs = []

    def log(msg):
        logs.append(msg)
        snippet = "\n".join(logs)[-500:]
        db.update_job(job_id, status="running", log=snippet)

    def _maybe_run(step, fn, args, label, timeout):
        if _is_stale(code, step, force):
            _run_with_timeout(fn, args, label, log, timeout)
        else:
            log(f"  ⏭ {label} 缓存新鲜，跳过")

    try:
        db.update_job(job_id, status="running")
        mode = "全量" if force else "缓存优先"
        log(f"▶ pipeline 开始: {code} ({market}) [{mode}]")

        is_st = _is_st(code)
        if is_st:
            log("  ℹ️ ST股检测到，跳过高级财务和信号步骤")

        _maybe_run("price",        _fetch_price,     [code, market, log], "价格",    20)
        _maybe_run("news",         _fetch_news,      [code, market, log], "新闻",    30)
        _maybe_run("fund_flow",    _fetch_fund_flow, [code, market, log], "主力资金", 30)
        _maybe_run("fundamentals", _fetch_financials,[code, market, log], "财务数据", 45)

        # 财务数据加载后重新分类，确保 speculative 等判断用上真实数字
        try:
            from classifier import classify_stock
            meta = classify_stock(code)
            log(f"  ✦ 重新分类: {meta.get('company_type')} / tier={meta.get('market_tier')}")
        except Exception as _ce:
            log(f"  ⚠️ 重新分类失败: {_ce}")

        if not is_st:
            _maybe_run("advanced",   _fetch_advanced,   [code, market, log], "高级财务",  30)
            _maybe_run("technicals", _fetch_technicals, [code, market, log], "技术支撑位", 20)
            _maybe_run("signals",    _fetch_signals,    [code, market, log], "投行信号",  30)

        _run_with_timeout(_run_analysis, [code, market, log, user_id], "AI分析", log, 180)

        log("✅ 完成")
        db.update_job(job_id, status="done", log="\n".join(logs)[-500:])

    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e),
                      log="\n".join(logs)[-500:])


def start_pipeline(user_id: int, code: str, market: str) -> int:
    """
    创建 job 记录并在后台线程启动 pipeline。
    返回 job_id 供前端轮询。
    """
    job_id = db.create_job(user_id, code, "add_stock")
    t = threading.Thread(target=run_pipeline, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


# ── US-45：分析层（用已有数据）────────────────────────

def run_analysis_only(job_id: int, code: str, market: str, user_id: int = None):
    """
    只跑 LLM 分析，不重爬任何数据。
    用 DB 里已有的财务/价格/新闻数据，<30s 完成。
    """
    logs = []

    def log(msg):
        logs.append(msg)
        db.update_job(job_id, status="running", log="\n".join(logs)[-500:])

    try:
        db.update_job(job_id, status="running")
        log(f"▶ 分析数据（用缓存）: {code}")
        _run_with_timeout(_run_analysis, [code, market, log, user_id], "AI分析", log, 180)
        log("✅ 完成")
        db.update_job(job_id, status="done", log="\n".join(logs)[-500:])
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs)[-500:])


def start_analysis_only(user_id: int, code: str, market: str) -> int:
    """启动「只跑分析」job，返回 job_id。"""
    job_id = db.create_job(user_id, code, "analyze_only")
    t = threading.Thread(target=run_analysis_only, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


# ── US-45：新闻层（1小时缓存）────────────────────────

def run_news_update(job_id: int, code: str, market: str):
    """
    只更新新闻，1小时内重复触发直接返回缓存结果。
    """
    logs = []

    def log(msg):
        logs.append(msg)
        db.update_job(job_id, status="running", log="\n".join(logs)[-500:])

    try:
        db.update_job(job_id, status="running")

        # 当日缓存检查：fetched_date 是日期字符串，今天有 ≥3 条即视为新鲜
        today_cn = datetime.now(CN_TZ).strftime("%Y-%m-%d")
        with db.get_conn() as c:
            count = c.execute(
                "SELECT COUNT(*) FROM stock_news WHERE code=? AND fetched_date=?",
                (code, today_cn)
            ).fetchone()[0]
        if count >= 3:
            log(f"  ℹ️ 今日已有 {count} 条新闻，跳过重复抓取")
            db.update_job(job_id, status="done", log="\n".join(logs)[-500:])
            return

        log(f"▶ 更新新闻: {code}")
        _run_with_timeout(_fetch_news, [code, market, log], "新闻", log, 30)
        log("✅ 新闻更新完成")
        db.update_job(job_id, status="done", log="\n".join(logs)[-500:])
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs)[-500:])


def start_news_update(user_id: int, code: str, market: str) -> int:
    """启动「更新新闻」job，返回 job_id。"""
    job_id = db.create_job(user_id, code, "news_update")
    t = threading.Thread(target=run_news_update, args=(job_id, code, market), daemon=True)
    t.start()
    return job_id


# ── 定时任务入口（所有用户所有自选股）─────────────────

def run_daily_all():
    """每天 08:00 CST 由 launchd 触发，对所有自选股跑 pipeline。"""
    codes = db.all_watched_codes()
    print(f"[daily] {len(codes)} 只股票")
    for code in codes:
        stock = db.get_stock(code)
        if not stock:
            continue
        market = stock.get("market", "nz")
        job_id = db.create_job(user_id=None, code=code, job_type="daily")
        run_pipeline(job_id, code, market)
        time.sleep(1)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "daily":
        run_daily_all()
    else:
        print("Usage: python3 pipeline.py daily")
