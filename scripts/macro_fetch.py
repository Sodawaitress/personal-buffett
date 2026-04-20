#!/usr/bin/env python3
"""
股票雷达 · 宏观数据层
CNY/USD汇率 · A股三大指数 · 铜/铁矿石 · Fear & Greed · FOMC声明
均为境外IP可访问接口
"""

import time, requests, feedparser, json
from datetime import datetime

SINA_HQ = "https://hq.sinajs.cn/list={symbols}"
HEADERS  = {"Referer": "https://finance.sina.com.cn"}


# ── CNY/USD 汇率 ──────────────────────────────────────
def fetch_cny_usd() -> dict:
    """
    CNY/USD汇率：open.er-api.com（免费，境外可用）
    新浪财经汇率接口在A股收盘后从NZ IP经常超时，此为更稳定替代。
    返回: {"rate": 7.23, "direction": "..."}
    """
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD",
                         timeout=10)
        data = r.json()
        rate = data["rates"].get("CNY", 0)
        # 无历史数据无法算change，标注汇率水平
        if rate >= 7.3:
            direction = "人民币偏弱（>7.3）"
        elif rate <= 7.0:
            direction = "人民币偏强（<7.0）"
        else:
            direction = "人民币中性区间"
        print(f"  💱 USD/CNY: {rate:.4f} — {direction}")
        return {"rate": round(rate, 4), "direction": direction}
    except Exception as e:
        print(f"  ⚠️ 汇率: {e}")
        return {}


# ── A股三大指数 ───────────────────────────────────────
def fetch_cn_indices() -> dict:
    """
    上证综指 / 深证成指 / 创业板指
    主力：AKShare（需A股交易时段），fallback：新浪（收盘后可能超时）
    返回: {"sh": {...}, "sz": {...}, "cyb": {...}}
    """
    # 先试 AKShare
    try:
        import akshare as ak
        mapping = {
            "sh000001": ("sh", "上证综指"),
            "sz399001": ("sz", "深证成指"),
            "sz399006": ("cyb", "创业板指"),
        }
        result = {}
        for symbol, (key, name) in mapping.items():
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                price  = float(latest.get("close", 0))
                prev   = float(df.iloc[-2].get("close", price)) if len(df) > 1 else price
                change = round((price - prev) / prev * 100, 2) if prev else 0
                result[key] = {"name": name, "price": price, "change": change}
                arrow = "📈" if change >= 0 else "📉"
                print(f"  {arrow} {name}: {price:.2f} ({change:+.2f}%)")
        if result:
            return result
    except Exception:
        pass

    # Fallback：新浪（盘中可用）
    symbols = "s_sh000001,s_sz399001,s_sz399006"
    labels  = {"s_sh000001": ("sh", "上证综指"),
               "s_sz399001": ("sz", "深证成指"),
               "s_sz399006": ("cyb", "创业板指")}
    result  = {}
    try:
        r = requests.get(SINA_HQ.format(symbols=symbols), headers=HEADERS, timeout=8)
        for line in r.text.strip().splitlines():
            if '="' not in line:
                continue
            sym    = line.split("hq_str_")[1].split("=")[0]
            fields = line.split('"')[1].split(",")
            if len(fields) < 4 or not fields[1]:
                continue
            key, name = labels.get(sym, (sym, sym))
            price  = float(fields[1])
            change = float(fields[3]) if fields[3] else 0
            result[key] = {"name": name, "price": price, "change": change}
    except Exception as e:
        print(f"  ⚠️ A股指数: {e}")
    return result


# ── 铜价 & 铁矿石（新浪期货）────────────────────────
def fetch_commodities() -> dict:
    """
    沪铜主力 + 铁矿石主力（大连商品交易所）
    对大西洋（焊接材料）和三一重工（钢铁成本）有直接影响
    """
    # 沪铜 CU 主力 + 铁矿石 I 主力
    symbols  = "nf_CU0,nf_I0"
    labels   = {"nf_CU0": "沪铜主力", "nf_I0": "铁矿石主力"}
    result   = {}
    try:
        r = requests.get(SINA_HQ.format(symbols=symbols),
                         headers=HEADERS, timeout=8)
        for line in r.text.strip().splitlines():
            if '="' not in line or not line.split('"')[1].strip():
                continue
            sym    = line.split("hq_str_")[1].split("=")[0]
            fields = line.split('"')[1].split(",")
            if len(fields) < 9:
                continue
            name   = labels.get(sym, sym)
            price  = float(fields[3]) if fields[3] else 0
            prev   = float(fields[2]) if fields[2] else price
            change = round((price - prev) / prev * 100, 2) if prev else 0
            result[sym] = {"name": name, "price": price, "change": change}
            arrow = "📈" if change >= 0 else "📉"
            print(f"  {arrow} {name}: {price:.0f} ({change:+.2f}%)")
    except Exception as e:
        print(f"  ⚠️ 大宗商品: {e}")
    return result


# ── CNN Fear & Greed Index ───────────────────────────
def fetch_fear_greed() -> dict:
    """
    CNN Fear & Greed Index (0-100)
    巴菲特逆向参照：极度恐惧=买入机会，极度贪婪=警惕
    """
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "https://production.dataviz.cnn.io/index/fearandgreed/current",
    ]
    for url in urls:
      try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        if r.status_code != 200 or not r.text.strip():
            continue
        data  = r.json()
        # Try different response shapes
        fg    = data.get("fear_and_greed") or data
        score = fg.get("score") or fg.get("value") or fg.get("current_value")
        label = fg.get("rating") or fg.get("value_classification", "")
        if score is None:
            continue
        score = float(score)
        # 巴菲特解读
        if score <= 25:
            buffett = "极度恐惧 → 巴菲特说：别人恐惧时我贪婪"
        elif score <= 45:
            buffett = "恐惧 → 市场情绪偏悲观，关注估值机会"
        elif score <= 55:
            buffett = "中性 → 无明显信号"
        elif score <= 75:
            buffett = "贪婪 → 注意安全边际收窄"
        else:
            buffett = "极度贪婪 → 巴菲特说：别人贪婪时我恐惧"
        print(f"  😱 Fear & Greed: {score:.0f} / {label} — {buffett}")
        return {"score": round(score), "label": label, "buffett": buffett}
      except Exception:
        continue
    print(f"  ⚠️ Fear & Greed: 所有URL均无法访问")
    return {}


# ── 美联储 FOMC 声明 ──────────────────────────────────
def fetch_fomc_news(limit: int = 3) -> list:
    """
    美联储官方 RSS —— 利率决议/会议纪要
    影响全球估值，尤其是高PE股票（阳光电源、FPH）
    """
    url = "https://www.federalreserve.gov/feeds/press_all.xml"
    items = []
    try:
        feed = feedparser.parse(url)
        for e in feed.entries[:limit * 3]:
            title = e.get("title", "")
            # 只要利率/货币政策相关
            keywords = ["Federal Open Market", "interest rate", "monetary policy",
                        "federal funds", "FOMC", "balance sheet"]
            if not any(k.lower() in title.lower() for k in keywords):
                continue
            items.append({
                "title":  title[:100],
                "link":   e.get("link", ""),
                "time":   e.get("published", "")[:16],
                "source": "Federal Reserve",
            })
            if len(items) >= limit:
                break
        if items:
            print(f"  🏦 FOMC: {len(items)} 条声明")
    except Exception as e:
        print(f"  ⚠️ FOMC RSS: {e}")
    return items


# ── A股/中国经济新闻（Google News RSS）────────────────
def fetch_cn_market_news(limit: int = 8) -> list:
    """
    中国财经市场新闻（Google News RSS，zh-CN）
    适合 CN 区域用户首页「本地新闻」栏。
    """
    QUERIES = [
        ("A股 股市 市场", "A股"),
        ("中国经济 宏观政策", "宏观"),
    ]
    CN_KEYWORDS = {
        "股市", "a股", "港股", "上证", "深证", "创业板", "沪深",
        "经济", "政策", "央行", "利率", "汇率", "通胀", "gdp",
        "上市", "基金", "债券", "人民币", "贸易", "出口", "进口",
    }
    items = []
    seen = set()
    for query, section in QUERIES:
        try:
            encoded = requests.utils.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            feed = feedparser.parse(url)
            for e in feed.entries[:15]:
                title = e.get("title", "")[:120]
                link = e.get("link", "")
                key = title[:40]
                if not title or key in seen:
                    continue
                tl = title.lower()
                if not any(k in tl for k in CN_KEYWORDS):
                    continue
                seen.add(key)
                source = e.get("source", {}).get("title", "Google News") if hasattr(e.get("source", ""), "get") else "Google News"
                items.append({
                    "title": title,
                    "link": link,
                    "source": source,
                    "time": e.get("published", "")[:16],
                    "section": section,
                })
                if len(items) >= limit:
                    break
        except Exception:
            pass
        if len(items) >= limit:
            break
    return items


# ── 挖掘机月销量（Google News RSS）────────────────────
def fetch_excavator_sales() -> dict:
    """
    中国工程机械工业协会每月公布挖掘机销量。
    先尝试AKShare，fallback到Google News RSS寻找最新月报。
    这是三一重工最直接的先行指标。
    """
    # 先尝试 AKShare
    try:
        import akshare as ak
        df = ak.macro_china_cx_pmi_yearly()
        # 如果有挖掘机相关数据最好；否则只用作fallback
    except Exception:
        pass

    # Google News RSS：找最新月度数据公告
    query   = "挖掘机 月销量 中国工程机械工业协会"
    encoded = requests.utils.quote(query)
    url     = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    items   = []
    try:
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:
            title = e.get("title", "")
            if any(k in title for k in ["销量", "销售", "挖掘机", "工程机械"]):
                items.append({
                    "title":  title[:100],
                    "link":   e.get("link", ""),
                    "time":   e.get("published", "")[:16],
                    "source": e.get("source", {}).get("title", "Google News"),
                })
        if items:
            print(f"  🚜 挖掘机销量: {items[0]['title'][:60]}")
    except Exception as e:
        print(f"  ⚠️ 挖掘机销量: {e}")

    return {"latest_news": items[:3]}


# ── 一键抓取所有宏观数据 ──────────────────────────────
def fetch_all_macro() -> dict:
    print("\n  🌍 宏观数据...")
    result = {}

    result["cny_usd"]      = fetch_cny_usd();      time.sleep(0.3)
    result["cn_indices"]   = fetch_cn_indices();    time.sleep(0.3)
    result["commodities"]  = fetch_commodities();   time.sleep(0.3)
    result["fear_greed"]   = fetch_fear_greed();    time.sleep(0.3)
    result["fomc"]         = fetch_fomc_news();     time.sleep(0.3)
    result["excavator"]    = fetch_excavator_sales()

    return result


if __name__ == "__main__":
    import json
    data = fetch_all_macro()
    print(json.dumps(data, ensure_ascii=False, indent=2))
