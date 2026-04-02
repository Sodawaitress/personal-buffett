#!/usr/bin/env python3
"""
股票雷达 · 抓取层
拉个股新闻、实时行情、北向资金、龙虎榜
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, time, requests
import feedparser
from datetime import datetime
import akshare as ak
from config import (
    WATCHLIST, HK_WATCHLIST, SECTOR_KEYWORDS,
    NEWS_PER_STOCK, RAW_OUTPUT, CN_TZ
)


# ── 个股行情（新浪财经，境外IP可用）────────────────
def _sina_prefix(code: str) -> str:
    """A股代码加交易所前缀"""
    return ("sh" if code.startswith(("6", "9")) else "sz") + code

def fetch_quotes():
    """一次请求拉全部自选股行情（新浪财经接口）"""
    print("  📊 拉取行情...")
    codes   = [c for _, c, _ in WATCHLIST]
    symbols = ",".join(_sina_prefix(c) for c in codes)
    name_map = {c: n for n, c, _ in WATCHLIST}
    quotes = {}
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={symbols}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=10
        )
        for line in r.text.strip().splitlines():
            # var hq_str_sh600031="名称,今开,昨收,现价,最高,最低,..."
            if '="' not in line:
                continue
            sym  = line.split("hq_str_")[1].split("=")[0]   # sh600031
            code = sym[2:]                                    # 600031
            fields = line.split('"')[1].split(",")
            if len(fields) < 9:
                continue
            price    = float(fields[3])
            prev     = float(fields[2])
            change   = round((price - prev) / prev * 100, 2) if prev else 0.0
            amount   = float(fields[9]) / 1e8                # 元 → 亿
            name     = name_map.get(code, fields[0])
            quotes[code] = {
                "name":     name,
                "code":     code,
                "price":    price,
                "change":   change,
                "amount":   amount,
                "turnover": 0.0,   # 新浪接口无换手率，后续可补
            }
            sign = "🔴" if change >= 0 else "🟢"
            print(f"    {sign} {name}({code}) {price} ({change:+.2f}%)")
    except Exception as e:
        print(f"    ⚠️ 行情: {e}")
    return quotes


# ── 个股新闻 ──────────────────────────────────────────
def fetch_stock_news(code: str, name: str) -> list:
    try:
        df = ak.stock_news_em(symbol=code)
        items = []
        for _, row in df.head(NEWS_PER_STOCK).iterrows():
            items.append({
                "title":   row.get("新闻标题", ""),
                "summary": row.get("新闻内容", "")[:200],
                "time":    str(row.get("发布时间", "")),
                "source":  row.get("文章来源", ""),
                "link":    row.get("新闻链接", ""),
            })
        print(f"    📰 {name}: {len(items)} 条新闻")
        return items
    except Exception as e:
        print(f"    ⚠️ {name} 新闻: {e}")
        return []


# ── 个股公告 ──────────────────────────────────────────
def fetch_announcements(code: str, name: str) -> list:
    try:
        df = ak.stock_notice_report(symbol=code)
        items = []
        for _, row in df.head(3).iterrows():
            items.append({
                "title": str(row.get("公告标题", row.get("title", ""))),
                "date":  str(row.get("公告日期", row.get("date", ""))),
                "link":  str(row.get("公告链接", row.get("url", ""))),
            })
        if items:
            print(f"    📋 {name}: {len(items)} 条公告")
        return items
    except Exception as e:
        # 公告接口有时不稳定，静默失败
        return []


# ── 北向资金（陆股通）────────────────────────────────
def fetch_north_bound() -> dict:
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        today = df.iloc[0]
        result = {
            "date":         str(today.get("日期", "")),
            "sh_net":       float(today.get("沪股通净买入", 0)),   # 亿元
            "sz_net":       float(today.get("深股通净买入", 0)),
            "total_net":    float(today.get("北向资金净买入", today.get("沪深港通净买入", 0))),
        }
        sign = "📈" if result["total_net"] >= 0 else "📉"
        print(f"  {sign} 北向资金净买入: {result['total_net']:.2f} 亿")
        return result
    except Exception as e:
        print(f"  ⚠️ 北向资金: {e}")
        return {}


# ── 龙虎榜（当天涨跌幅超5%个股机构席位）────────────
def fetch_lhb(codes: list) -> list:
    """检查自选股是否上了龙虎榜"""
    try:
        df = ak.stock_lhb_detail_em(start_date=datetime.now(CN_TZ).strftime("%Y%m%d"),
                                     end_date=datetime.now(CN_TZ).strftime("%Y%m%d"))
        if df is None or df.empty:
            return []
        hits = []
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            if code in codes:
                hits.append({
                    "name":   row.get("名称", ""),
                    "code":   code,
                    "reason": row.get("上榜原因", ""),
                    "buy":    float(row.get("买入总金额", 0)) / 1e8,
                    "sell":   float(row.get("卖出总金额", 0)) / 1e8,
                })
        if hits:
            print(f"  🔔 龙虎榜命中: {[h['name'] for h in hits]}")
        return hits
    except Exception as e:
        print(f"  ⚠️ 龙虎榜: {e}")
        return []


# ── 板块新闻（政策面）────────────────────────────────
def fetch_sector_news() -> list:
    """从财联社快讯抓板块/政策相关新闻（stock_news_main_cx，境外IP可访问）"""
    try:
        df = ak.stock_news_main_cx()
        items = []
        seen = set()
        for _, row in df.iterrows():
            tag     = str(row.get("tag", ""))
            summary = str(row.get("summary", ""))
            url     = str(row.get("url", ""))
            text    = tag + summary
            if any(kw in text for kw in SECTOR_KEYWORDS):
                key = summary[:40]
                if key not in seen:
                    seen.add(key)
                    items.append({
                        "title": summary[:120],
                        "time":  "",   # 财联社接口不返回时间字段
                        "link":  url,
                    })
            if len(items) >= 8:
                break
        print(f"  📡 板块快讯: {len(items)} 条")
        return items
    except Exception as e:
        print(f"  ⚠️ 板块快讯: {e}")
        return []


# ── 大股东增减持 ──────────────────────────────────────
def fetch_insider_changes(code: str, name: str) -> list:
    """拉大股东/高管增减持公告"""
    try:
        df = ak.stock_hszg_em(symbol=code)
        if df is None or df.empty:
            return []
        items = []
        for _, row in df.head(3).iterrows():
            change_type = str(row.get("变动类型", row.get("类型", "")))
            holder      = str(row.get("股东名称", row.get("变动股东", "")))
            ratio       = str(row.get("变动比例", row.get("占总股本比例", "")))
            date_str    = str(row.get("截止日期", row.get("公告日期", "")))
            items.append({
                "holder": holder[:20],
                "type":   change_type,
                "ratio":  ratio,
                "date":   date_str[:10],
            })
        if items:
            print(f"    📋 {name} 增减持: {len(items)} 条")
        return items
    except Exception:
        return []


# ── 主力资金流向 ──────────────────────────────────────
def fetch_fund_flow(code: str, name: str) -> dict:
    """拉个股主力资金净流入（近5日）"""
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith(("6","9")) else "sz")
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        result = {
            "date":       str(latest.get("日期", ""))[:10],
            "main_net":   float(latest.get("主力净流入-净额", 0) or 0) / 1e8,
            "super_net":  float(latest.get("超大单净流入-净额", 0) or 0) / 1e8,
            "big_net":    float(latest.get("大单净流入-净额", 0) or 0) / 1e8,
            "main_ratio": float(latest.get("主力净流入-净占比", 0) or 0),
        }
        direction = "📈流入" if result["main_net"] >= 0 else "📉流出"
        print(f"    💰 {name} 主力 {direction} {abs(result['main_net']):.2f}亿")
        return result
    except Exception:
        return {}


# ── 国际信息源（Google News RSS）─────────────────────
# 每只股 / 每个板块的英文查询词
INTL_QUERIES = {
    # 个股竞争对手 & 公司本身
    "600031": [
        ("SANY Heavy Equipment earnings outlook",        "三一重工"),
        ("Caterpillar Komatsu excavator demand",         "竞品参照"),
    ],
    "300274": [
        ("SolarEdge Enphase inverter earnings results",  "竞品参照"),
        ("China solar storage export market 2026",       "阳光电源"),
    ],
    "600196": [
        ("Fosun Pharma clinical trial approval",         "复星医药"),
        ("China innovative drug FDA EMA approval",       "创新药"),
    ],
    # 板块/宏观
    "_sector": [
        ("IRA solar energy storage policy tariff",       "美国能源政策"),
        ("EU Europe renewable energy storage tender",    "欧洲储能"),
        ("China construction equipment global demand",   "工程机械出海"),
        ("China pharma drug licensing out deal",         "医药出海"),
    ],
}

def fetch_international_news() -> dict:
    """通过 Google News RSS 抓国际资讯，按股票代码分组"""
    print("  🌐 国际资讯...")
    result = {}   # code -> list of items  +  "_sector" -> list

    for key, queries in INTL_QUERIES.items():
        items = []
        seen  = set()
        for query, label in queries:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    title = entry.get("title", "")[:120]
                    link  = entry.get("link", "")
                    src   = entry.get("source", {}).get("title", "Google News")
                    pub   = entry.get("published", "")[:10]
                    key2  = title[:40]
                    if key2 not in seen:
                        seen.add(key2)
                        items.append({
                            "title":  title,
                            "label":  label,
                            "link":   link,
                            "source": src,
                            "time":   pub,
                        })
            except Exception:
                pass
            time.sleep(0.3)
        if items:
            result[key] = items
            tag = key if key == "_sector" else key
            print(f"    🌐 {tag}: {len(items)} 条国际资讯")

    return result


# ── 主逻辑 ────────────────────────────────────────────
def main():
    now = datetime.now(CN_TZ)
    print(f"\n📈 股票雷达 抓取开始 {now.strftime('%Y-%m-%d %H:%M CST')}")

    output = {
        "date":           now.strftime("%Y-%m-%d"),
        "time":           now.isoformat(),
        "quotes":         {},
        "news":           {},
        "announcements":  {},
        "insider":        {},
        "fund_flow":      {},
        "north_bound":    {},
        "lhb":            [],
        "sector_news":    [],
        "intl_news":      {},
    }

    # 行情
    output["quotes"] = fetch_quotes()
    time.sleep(1)

    # 个股新闻 + 公告 + 增减持 + 资金流向
    print("\n  📰 个股动态：")
    codes = [code for _, code, _ in WATCHLIST]
    for name, code, _ in WATCHLIST:
        output["news"][code]          = fetch_stock_news(code, name)
        output["announcements"][code] = fetch_announcements(code, name)
        output["insider"][code]       = fetch_insider_changes(code, name)
        output["fund_flow"][code]     = fetch_fund_flow(code, name)
        time.sleep(0.5)

    # 北向资金
    print("\n  🏦 资金面：")
    output["north_bound"] = fetch_north_bound()

    # 龙虎榜
    output["lhb"] = fetch_lhb(codes)

    # 板块快讯
    print("\n  🗞️ 板块政策快讯：")
    output["sector_news"] = fetch_sector_news()

    # 国际资讯
    print("\n  🌐 国际信息源：")
    output["intl_news"] = fetch_international_news()

    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_news = sum(len(v) for v in output["news"].values())
    print(f"\n✅ 完成：{len(output['quotes'])} 只股行情，{total_news} 条新闻，"
          f"{len(output['sector_news'])} 条板块快讯 → {RAW_OUTPUT}")


if __name__ == "__main__":
    main()
