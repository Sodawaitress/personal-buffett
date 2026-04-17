#!/usr/bin/env python3
"""
股票雷达 · 抓取层
拉个股新闻、实时行情、北向资金、龙虎榜
"""

import sys, os
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import json, time, requests
import feedparser

from scripts.stock_fetch_financials import fetch_cn_advanced, fetch_cn_financials, fetch_cn_signals

from datetime import datetime
import akshare as ak
from scripts.config import (
    WATCHLIST, HK_WATCHLIST, SECTOR_KEYWORDS,
    NEWS_PER_STOCK, RAW_OUTPUT, CN_TZ
)


# ── 个股行情（新浪财经，境外IP可用）────────────────
def _sina_prefix(code: str) -> str:
    """A股代码加交易所前缀"""
    return ("sh" if code.startswith(("6", "9")) else "sz") + code

def fetch_quotes(cn_stocks: list = None):
    """
    一次请求拉全部自选股行情（新浪财经接口）。
    cn_stocks: [(name, code), ...] 列表。为 None 时回退到硬编码 WATCHLIST（兼容旧调用）。
    """
    print("  📊 拉取行情...")
    if cn_stocks is None:
        cn_stocks = [(n, c) for n, c, _ in WATCHLIST]
    codes    = [c for _, c in cn_stocks]
    name_map = {c: n for n, c in cn_stocks}
    symbols  = ",".join(_sina_prefix(c) for c in codes)
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


# ── A股财务数据（ROE / 净利率 / 负债率 + PE/PB 历史百分位）────
def fetch_north_bound() -> dict:
    """
    AKShare stock_hsgt_fund_flow_summary_em() 返回列：
    交易日 | 类型 | 板块 | 资金方向 | 成交净买额 | 资金净流入 | ...
    北向 = 资金方向=='北向'；沪股通/深股通 由 板块 区分。
    资金净流入 单位：百万元，转亿元需 /100。
    """
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        north = df[df["资金方向"] == "北向"]
        if north.empty:
            print("  ⚠️ 北向资金：无北向数据行")
            return {}

        def _get_net(board: str) -> float:
            row = north[north["板块"] == board]
            if row.empty:
                return 0.0
            val = row.iloc[0].get("资金净流入", 0)
            return float(val) / 100  # 百万→亿

        sh_net = _get_net("沪股通")
        sz_net = _get_net("深股通")
        date_str = str(north.iloc[0].get("交易日", ""))
        total_net = sh_net + sz_net
        result = {
            "date":      date_str,
            "sh_net":    sh_net,
            "sz_net":    sz_net,
            "total_net": total_net,
        }
        sign = "📈" if total_net >= 0 else "📉"
        print(f"  {sign} 北向资金净买入: {total_net:.2f} 亿（沪 {sh_net:.1f} + 深 {sz_net:.1f}）")
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


# ── 技术支撑位（MA均线 + VWAP成本参考）────────────────
def fetch_cn_technicals(code: str) -> dict:
    """
    用新浪K线接口（NZ IP可用）计算技术支撑位：
      - ma20 / ma60 / ma120 / ma250: 均线支撑
      - vwap60 / vwap120: 近60/120日成交量加权均价（机构成本参考）
      - price_vs_ma*: 当前价偏离均线的百分比
    返回空 dict 表示失败。
    """
    import requests as req
    try:
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
        r = req.get(
            "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData",
            params={"symbol": f"{prefix}{code}", "scale": 240, "ma": 5, "datalen": 280},
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=12,
        )
        bars = r.json()
        if not bars or len(bars) < 20:
            return {}

        closes  = [float(b["close"])  for b in bars]
        volumes = [float(b["volume"]) for b in bars]

        def _ma(n):
            if len(closes) < n:
                return None
            return round(sum(closes[-n:]) / n, 2)

        def _vwap(n):
            if len(closes) < n:
                return None
            cv = sum(closes[-n][i] * volumes[-n:][i] for i in range(n)) if False else None
            c_slice = closes[-n:]
            v_slice = volumes[-n:]
            total_v = sum(v_slice)
            if total_v == 0:
                return None
            return round(sum(c * v for c, v in zip(c_slice, v_slice)) / total_v, 2)

        current = closes[-1]

        def _pct(ma_val):
            if ma_val is None or ma_val == 0:
                return None
            return round((current - ma_val) / ma_val * 100, 1)

        result = {
            "ma20":  _ma(20),   "ma60":  _ma(60),
            "ma120": _ma(120),  "ma250": _ma(250),
            "vwap60":  _vwap(60),
            "vwap120": _vwap(120),
        }
        result["price_vs_ma20"]  = _pct(result["ma20"])
        result["price_vs_ma60"]  = _pct(result["ma60"])
        result["price_vs_ma120"] = _pct(result["ma120"])
        result["price_vs_ma250"] = _pct(result["ma250"])
        result["price_vs_vwap60"]  = _pct(result["vwap60"])
        result["price_vs_vwap120"] = _pct(result["vwap120"])
        return result
    except Exception:
        return {}


# ── 新闻源配置 ────────────────────────────────────────
# 摩根大通研究报告 RSS
# 注意: JPMorgan 官方 RSS 已下线，改用 Google News 聚合 (见 INTL_QUERIES)
# 英文新闻分析已在 _analyze_news_signals() 中支持
JPMORGANCHASE_SOURCES = []  # 暂时禁用，等待替换为可用来源

# Google News 搜索词，用于抓取摩根大通市场观点
JPMORGANCHASE_QUERIES = [
    "JPMorgan market outlook 2026",
    "JPMorgan research report investment",
    "Jamie Dimon economy forecast",
    "JPMorgan China market analysis",
    "JPMorgan Asia investment strategy",
]

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


def fetch_jpmorganchase_news() -> list:
    """从摩根大通官方 RSS 抓取最新新闻和研究报告"""
    print("  📊 摩根大通新闻...")
    items = []
    seen = set()

    import requests as _req
    for query in JPMORGANCHASE_QUERIES:
        try:
            q = _req.utils.quote(query)
            url = f"https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "")[:120]
                link = entry.get("link", "")
                pub = entry.get("published", "")[:10]
                summary = entry.get("summary", "")[:200]
                key = title[:40]
                if key and key not in seen:
                    seen.add(key)
                    items.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": "摩根大通",
                        "time": pub,
                    })
        except Exception as e:
            pass
        time.sleep(0.3)

    if items:
        print(f"    📊 摩根大通: {len(items)} 条新闻")
    return items


# ── A股财报日历 ───────────────────────────────────────
def fetch_cn_earnings_calendar(codes: list) -> list:
    """
    从东方财富获取自选股的近期财报披露日期。
    提前知道哪天出季报，巴菲特视角：重要业绩日前后是关键观察窗口。
    """
    events = []
    try:
        df = ak.stock_report_fund_em(symbol="全部", indicator="预约披露时间")
        if df is None or df.empty:
            return []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", ""))
            if code in codes:
                events.append({
                    "code":  code,
                    "name":  str(row.get("股票简称", "")),
                    "date":  str(row.get("预约披露时间", ""))[:10],
                    "type":  str(row.get("报告类型", "")),
                })
        events.sort(key=lambda x: x["date"])
        if events:
            print(f"  📅 A股财报日历: {len(events)} 只有近期财报")
    except Exception as e:
        print(f"  ⚠️ 财报日历: {e}")
    return events


# ── 主逻辑 ────────────────────────────────────────────
def _load_cn_stocks_from_db() -> list:
    """
    从 DB 读取所有用户自选股中市场为 cn 的股票，返回 [(name, code), ...]（去重）。
    找不到 DB 时回退到 WATCHLIST。
    """
    try:
        import db
        rows = db.get_all_cn_watchlist_stocks()   # [(code, name), ...]
        if rows:
            seen = set()
            result = []
            for code, name in rows:
                if code not in seen:
                    seen.add(code)
                    result.append((name or code, code))
            return result
    except Exception as e:
        print(f"  ⚠️ 从DB读股票列表失败，回退到 WATCHLIST: {e}")
    return [(n, c) for n, c, _ in WATCHLIST]


def main():
    now = datetime.now(CN_TZ)
    print(f"\n📈 股票雷达 抓取开始 {now.strftime('%Y-%m-%d %H:%M CST')}")

    # 从 DB 动态读所有用户的 A 股自选股
    cn_stocks = _load_cn_stocks_from_db()
    codes     = [c for _, c in cn_stocks]
    print(f"  📋 本次抓取 {len(cn_stocks)} 只 A 股：{[c for _,c in cn_stocks]}")

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
        "cn_earnings":    [],   # A股财报日历
    }

    # 行情
    output["quotes"] = fetch_quotes(cn_stocks)
    time.sleep(1)

    # 个股新闻 + 公告 + 增减持 + 资金流向
    print("\n  📰 个股动态：")
    for name, code in cn_stocks:
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

    # 摩根大通新闻
    print("\n  📊 专业机构资讯：")
    output["jpm_news"] = fetch_jpmorganchase_news()

    # A股财报日历
    print("\n  📅 财报日历：")
    output["cn_earnings"] = fetch_cn_earnings_calendar(codes)

    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_news = sum(len(v) for v in output["news"].values())
    print(f"\n✅ 完成：{len(output['quotes'])} 只股行情，{total_news} 条新闻，"
          f"{len(output['sector_news'])} 条板块快讯 → {RAW_OUTPUT}")


if __name__ == "__main__":
    main()
