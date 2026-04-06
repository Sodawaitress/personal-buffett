"""
Personal Buffett · NZ Market Data Fetcher
Uses yfinance for NZX quotes, fundamentals, and news
RBNZ RSS · NZX announcements · Earnings calendar
"""

import time
import feedparser
import yfinance as yf
from datetime import datetime, timezone, timedelta
from nz_profiles import NZ_PROFILES

NZ_TZ = timezone(timedelta(hours=12))  # NZST


def fetch_nz_quote(ticker: str) -> dict:
    """Fetch current quote + key fundamentals for one NZX stock."""
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="30d")

        price   = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev    = info.get("previousClose", price)
        change  = round((price - prev) / prev * 100, 2) if prev else 0.0

        # 30-day sparkline prices
        sparkline = []
        if not hist.empty:
            sparkline = [round(p, 2) for p in hist["Close"].tolist()]

        return {
            "ticker":     ticker,
            "name":       info.get("shortName", ticker),
            "price":      round(price, 2),
            "change":     change,
            "currency":   info.get("currency", "NZD"),
            "market_cap": info.get("marketCap"),
            "pe":         info.get("trailingPE"),
            "pb":         info.get("priceToBook"),
            "roe":        info.get("returnOnEquity"),
            "revenue":    info.get("totalRevenue"),
            "net_income": info.get("netIncomeToCommon"),
            "div_yield":  info.get("dividendYield"),
            "52w_high":   info.get("fiftyTwoWeekHigh"),
            "52w_low":    info.get("fiftyTwoWeekLow"),
            "sparkline":  sparkline,
        }
    except Exception as e:
        print(f"  ⚠️ {ticker}: {e}")
        return {"ticker": ticker, "price": None, "change": 0, "sparkline": []}


def fetch_nz_news(ticker: str, limit: int = 5) -> list:
    """Fetch recent news for a NZX stock via yfinance."""
    try:
        t    = yf.Ticker(ticker)
        news = t.news or []
        items = []
        for n in news[:limit]:
            content = n.get("content", {})
            items.append({
                "title":  content.get("title", ""),
                "link":   content.get("canonicalUrl", {}).get("url", "") or n.get("link", ""),
                "source": content.get("provider", {}).get("displayName", "Yahoo Finance"),
                "time":   content.get("pubDate", "")[:10],
            })
        return [i for i in items if i["title"]]
    except Exception:
        return []


def fetch_nz_market_news() -> list:
    """RNZ Business + Stuff.co.nz for NZ market-wide news."""
    sources = [
        ("https://www.rnz.co.nz/rss/business.xml", "RNZ Business"),
        ("https://www.stuff.co.nz/rss", "Stuff"),
    ]
    # 财经关键词过滤（Stuff 是综合源）
    BUSINESS_KEYWORDS = {
        "economy", "market", "stock", "share", "trade", "inflation",
        "gdp", "export", "import", "housing", "property", "bank",
        "nzx", "dollar", "nzd", "investment", "fund", "business",
        "economic", "financial", "finance", "rate", "nz", "新西兰",
    }
    items = []
    seen  = set()
    for url, source in sources:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:20]:
                title = e.get("title", "")[:120]
                link  = e.get("link", "")
                key   = title[:40]
                if not key or key in seen:
                    continue
                # Stuff 用关键词过滤，RNZ Business 直接用
                if source == "Stuff":
                    title_lower = title.lower()
                    if not any(kw in title_lower for kw in BUSINESS_KEYWORDS):
                        continue
                seen.add(key)
                items.append({
                    "title":  title,
                    "link":   link,
                    "source": source,
                    "time":   e.get("published", "")[:16],
                })
                if len(items) >= 10:
                    break
        except Exception:
            pass
        time.sleep(0.3)
        if len(items) >= 10:
            break
    return items[:10]


def fetch_nzx50() -> dict:
    """Fetch NZX50 index today."""
    try:
        t    = yf.Ticker("^NZ50")
        info = t.info
        hist = t.history(period="5d")
        price  = info.get("regularMarketPrice") or (hist["Close"].iloc[-1] if not hist.empty else None)
        prev   = info.get("regularMarketPreviousClose")
        change = round((price - prev) / prev * 100, 2) if price and prev else 0.0
        return {"price": round(price, 0) if price else None, "change": change}
    except Exception:
        return {}


def fetch_all_nz_quotes() -> dict:
    """Fetch quotes for all profiled NZ stocks."""
    print("  📊 Fetching NZX quotes…")
    results = {}
    for ticker in NZ_PROFILES:
        q = fetch_nz_quote(ticker)
        if q.get("price"):
            results[ticker] = q
            sign = "🔴" if q["change"] >= 0 else "🟢"
            print(f"    {sign} {q['name']} {q['price']} ({q['change']:+.2f}%)")
        time.sleep(0.4)
    return results


# ── RBNZ 利率决议 / 货币政策声明 ─────────────────────
def fetch_rbnz_news(limit: int = 3) -> list:
    """
    储备银行相关新闻：官方 RSS 已 403，改用 RNZ Business 过滤关键词。
    """
    url = "https://www.rnz.co.nz/rss/business.xml"
    keywords = ["reserve bank", "rbnz", "ocr", "official cash rate",
                "monetary policy", "interest rate", "inflation", "mpc"]
    items = []
    try:
        feed = feedparser.parse(url)
        for e in feed.entries[:30]:
            title = e.get("title", "")
            if any(k in title.lower() for k in keywords):
                items.append({
                    "title":  title[:120],
                    "link":   e.get("link", ""),
                    "time":   e.get("published", "")[:16],
                    "source": "RBNZ via RNZ",
                })
            if len(items) >= limit:
                break
        if items:
            print(f"  🇳🇿 RBNZ news: {items[0]['title'][:60]}")
        else:
            print("  ℹ️ No RBNZ keywords found in RNZ Business today")
    except Exception as e:
        print(f"  ⚠️ RBNZ/RNZ RSS: {e}")
    return items


# ── NZX公司公告（via yfinance）────────────────────────
def fetch_nzx_announcements(tickers: list = None, limit_per: int = 2) -> dict:
    """
    通过 yfinance 获取 NZX 上市公司近期新闻/公告。
    比 fetch_nz_news 更聚焦于公司公告类内容。
    返回: {ticker: [announcement_items]}
    """
    if tickers is None:
        # 只抓 A/B+ 级别的核心持仓
        tickers = [t for t, p in NZ_PROFILES.items() if p.get("grade") in ("A", "B+")]

    results = {}
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            news = t.news or []
            items = []
            for n in news[:limit_per * 2]:
                content = n.get("content", {})
                title   = content.get("title", "")
                # 过滤：只要公告类内容
                promo = content.get("contentType", "")
                if promo in ("PROMOTED", "AD"):
                    continue
                items.append({
                    "title":  title[:120],
                    "link":   content.get("canonicalUrl", {}).get("url", "") or n.get("link", ""),
                    "source": content.get("provider", {}).get("displayName", "NZX"),
                    "time":   content.get("pubDate", "")[:10],
                })
                if len(items) >= limit_per:
                    break
            if items:
                results[ticker] = items
                print(f"    📋 {ticker}: {items[0]['title'][:50]}")
            time.sleep(0.3)
        except Exception:
            pass
    return results


# ── NZX 财报日历（近30天内有财报的股票）──────────────
def fetch_nzx_earnings_calendar() -> list:
    """
    yfinance calendar：获取NZX profiled股票的下一次财报日期。
    帮助提前布局，避免被业绩雷炸到。
    """
    events = []
    for ticker in NZ_PROFILES:
        try:
            t   = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None or cal.empty:
                continue
            # calendar 是 DataFrame，列是日期，行是 Earnings Date / Revenue 等
            col = cal.columns[0] if not cal.empty else None
            if col is None:
                continue
            date_val = str(col)[:10]
            name     = NZ_PROFILES[ticker].get("name", ticker)
            events.append({
                "ticker": ticker,
                "name":   name,
                "date":   date_val,
            })
        except Exception:
            pass
        time.sleep(0.2)

    events.sort(key=lambda x: x["date"])
    if events:
        print(f"  📅 NZX财报日历: {len(events)} 只股票有近期财报")
    return events
