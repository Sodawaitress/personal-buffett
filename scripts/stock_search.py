#!/usr/bin/env python3
"""
私人巴菲特 · 股票搜索
双引擎：AKShare（A股模糊搜名/代码）+ yfinance（港/美/NZ Ticker 直查）

A股列表持久化缓存到 data/cn_stocks.json，有效期 24 小时。
Flask 重启后毫秒级加载，无需每次重新下载。
"""
import sys, os, re, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cn_stocks.json")
_CACHE_TTL  = 86400   # 24 小时

_CN_CACHE   = None
_CN_LOADING = False
_CN_READY   = threading.Event()


def _load_cn():
    global _CN_CACHE, _CN_LOADING
    if _CN_CACHE is not None:
        return _CN_CACHE
    if _CN_LOADING:
        _CN_READY.wait(timeout=60)
        return _CN_CACHE or []
    _CN_LOADING = True
    try:
        # 1. 尝试从文件缓存读取
        if os.path.exists(_CACHE_FILE):
            age = time.time() - os.path.getmtime(_CACHE_FILE)
            if age < _CACHE_TTL:
                with open(_CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    _CN_CACHE = [tuple(x) for x in data]
                    return _CN_CACHE

        # 2. 缓存不存在或已过期，从 AKShare 下载
        import akshare as ak
        df = ak.stock_info_a_code_name()
        cols = list(df.columns)
        rows = [(str(r[cols[0]]), str(r[cols[1]])) for _, r in df.iterrows()]
        _CN_CACHE = rows

        # 3. 写入文件缓存
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)

    except Exception:
        _CN_CACHE = _CN_CACHE or []
    finally:
        _CN_LOADING = False
        _CN_READY.set()
    return _CN_CACHE


def _prewarm():
    t = threading.Thread(target=_load_cn, daemon=True)
    t.start()

_prewarm()


def _search_cn(q: str, limit: int = 8) -> list:
    stocks = _load_cn()
    q_l = q.lower()
    out = []
    for code, name in stocks:
        if q_l in code or q_l in name.lower():
            out.append({
                "code":     code,
                "name":     name,
                "market":   "cn",
                "exchange": "SH" if code.startswith("6") else "SZ",
                "currency": "CNY",
            })
            if len(out) >= limit:
                break
    return out


def _search_yf(ticker: str) -> list:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        short = info.get("shortName") or info.get("longName")
        if not short:
            return []
        exch = info.get("exchange", "")
        curr = info.get("currency", "USD")
        code = ticker.upper()
        if code.endswith(".NZ") or curr == "NZD":
            market = "nz"
        elif code.endswith(".HK") or exch in ("HKG", "HKSE") or curr == "HKD":
            market = "hk"
        else:
            market = "us"
        return [{"code": code, "name": short,
                 "market": market, "exchange": exch, "currency": curr}]
    except Exception:
        return []


def search(q: str, limit: int = 10) -> list:
    q = q.strip()
    if not q:
        return []

    results, seen = [], set()

    def _add(items):
        for r in items:
            if r["code"] not in seen:
                seen.add(r["code"])
                results.append(r)

    has_cn  = any('\u4e00' <= c <= '\u9fff' for c in q)
    is_num  = q.isdigit()
    has_dot = '.' in q
    alpha   = bool(re.match(r'^[A-Za-z]', q))

    if has_cn or is_num or (not alpha and len(q) <= 7):
        _add(_search_cn(q, limit=limit))

    if alpha or has_dot:
        ticker = q.upper()
        _add(_search_yf(ticker))
        if not has_dot:
            for sfx in (".NZ", ".HK"):
                if len(results) < limit:
                    _add(_search_yf(ticker + sfx))

    if not results:
        _add(_search_cn(q, limit=limit))

    return results[:limit]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "茅台"
    for item in search(query):
        print(item)
