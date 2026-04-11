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

            # 通过 signals 参数保存其他财务指标
            db.upsert_fundamentals(
                code,
                annual=[],
                pe_current=fundamentals.get("pe_current"),
                pb_current=fundamentals.get("pb_current"),
                signals={k:v for k,v in fundamentals.items() if v is not None}
            )
            pe = fundamentals.get("pe_current")
            pb = fundamentals.get("pb_current")
            log(f"       PE={pe if pe else '?'} PB={pb if pb else '?'}")
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


def _run_analysis(code, market, log, user_id=None):
    """Step 4: 巴菲特++分析"""
    log("  [4/4] 运行巴菲特分析…")
    try:
        from buffett_analyst import analyze_stock_v2
        news        = db.get_stock_news(code, days=7)
        price       = db.get_latest_price(code)
        ff          = db.get_fund_flow(code) if market == "cn" else {}
        fundamentals= db.get_fundamentals(code)  # 所有市场都支持基本面数据
        stock       = db.get_stock(code)

        # 查用户持仓成本
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
                        log(f"       持仓成本 ¥{entry_price:.2f}（{buy_date or '未记日期'}）")
            except Exception:
                pass

        result = analyze_stock_v2(
            code=code,
            name=stock.get("name", code) if stock else code,
            market=market,
            price=price,
            news=news,
            fund_flow=ff,
            fundamentals=fundamentals,
            signals=fundamentals.get("signals", {}),
            entry_price=entry_price,
            buy_date=buy_date,
        )
        if result:
            today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
            db.save_analysis(
                code=code,
                period="daily",
                analysis_date=today,
                **result,
            )
            log(f"       评级: {result.get('grade','—')} · {result.get('conclusion','')}")
    except Exception as e:
        log(f"       ⚠️ 分析失败: {e}")


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


# ── 主 pipeline ────────────────────────────────────────

def run_pipeline(job_id: int, code: str, market: str, user_id: int = None):
    """
    在后台线程中运行。每步有独立超时（35s），不会因单步卡住拖死整个分析。
    """
    logs = []

    def log(msg):
        logs.append(msg)
        snippet = "\n".join(logs)[-500:]
        db.update_job(job_id, status="running", log=snippet)

    try:
        db.update_job(job_id, status="running")
        log(f"▶ pipeline 开始: {code} ({market})")

        is_st = _is_st(code)
        if is_st:
            log("  ℹ️ ST股检测到，跳过高级财务和信号步骤")

        _run_with_timeout(_fetch_price,    [code, market, log], "价格",    log, 20)
        _run_with_timeout(_fetch_news,     [code, market, log], "新闻",    log, 30)
        _run_with_timeout(_fetch_fund_flow,[code, market, log], "主力资金", log, 30)
        _run_with_timeout(_fetch_financials,[code, market, log], "财务数据",log, 45)

        if not is_st:
            _run_with_timeout(_fetch_advanced,   [code, market, log], "高级财务",  log, 30)
            _run_with_timeout(_fetch_technicals, [code, market, log], "技术支撑位",log, 20)
            _run_with_timeout(_fetch_signals,    [code, market, log], "投行信号",  log, 30)

        _run_with_timeout(_run_analysis,   [code, market, log, user_id], "AI分析",  log, 180)

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
