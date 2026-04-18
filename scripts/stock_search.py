#!/usr/bin/env python3
"""
私人巴菲特 · 股票搜索
三引擎：
  1. A股中文名/代码 精确子串匹配
  2. A股拼音首字母匹配（gzmt → 贵州茅台）
  3. yfinance Ticker 直查（港/美/NZ）

常见港股中文名内置映射（腾讯/阿里/美团等）

A股列表持久化缓存到 data/cn_stocks.json，有效期 24 小时。
拼音索引缓存到 data/cn_stocks_pinyin.json，与 A股缓存同步更新。
"""
import sys, os, re, json, time, threading
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

_CACHE_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "cn_stocks.json")
_PINYIN_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cn_stocks_pinyin.json")
_ETF_CACHE_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "cn_etfs.json")
_FUND_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cn_funds.json")
_CACHE_TTL       = 604800  # 7 天（A股列表变化极慢）
_FUND_CACHE_TTL  = 86400   # 1 天

_CN_CACHE    = None   # [(code, name), ...]
_PY_INDEX    = None   # [(code, name, initials, full_pinyin), ...]
_CN_LOADING  = False
_CN_READY    = threading.Event()
_ETF_CACHE   = None   # [(code, name), ...]  — ETF traded on exchange
_ETF_LOADING = False
_ETF_READY   = threading.Event()
_FUND_CACHE  = None   # [(code, name), ...]  — 场外基金（全量，~26000）
_FUND_LOADING = False
_FUND_READY  = threading.Event()

# ── 搜索结果缓存（1h TTL，避免重复 yfinance 请求）────────
_RESULT_CACHE = {}          # query_key → (results_list, expires_ts)
_RESULT_CACHE_TTL = 3600    # 1 小时
_RESULT_CACHE_LOCK = threading.Lock()

def _cache_get(key):
    with _RESULT_CACHE_LOCK:
        entry = _RESULT_CACHE.get(key)
        if entry and time.time() < entry[1]:
            return entry[0]
    return None

def _cache_set(key, value):
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE[key] = (value, time.time() + _RESULT_CACHE_TTL)
        # 顺手清过期条目（最多保留 500 条）
        if len(_RESULT_CACHE) > 500:
            now = time.time()
            expired = [k for k, v in _RESULT_CACHE.items() if v[1] < now]
            for k in expired:
                del _RESULT_CACHE[k]

# ── 常见港股中文名 → HK Ticker 映射 ─────────────────────
HK_NAMES = {
    "腾讯": "0700.HK", "腾讯控股": "0700.HK",
    "阿里": "9988.HK", "阿里巴巴": "9988.HK",
    "美团": "3690.HK", "美团点评": "3690.HK",
    "京东": "9618.HK", "京东集团": "9618.HK",
    "小米": "1810.HK", "小米集团": "1810.HK",
    "快手": "1024.HK",
    "中国移动": "0941.HK",
    "中国电信": "0728.HK",
    "中国联通": "0762.HK",
    "汇丰": "0005.HK", "汇丰控股": "0005.HK",
    "港交所": "0388.HK", "香港交易所": "0388.HK",
    "友邦保险": "1299.HK",
    "比亚迪股份": "1211.HK",
    "中芯国际": "0981.HK",
    "网易": "9999.HK",
    "百度": "9888.HK",
    "九福来": "8611.HK",
}

# ── 常见拼音别名（不规则或简称）────────────────────────
PINYIN_ALIAS = {
    "maotai": "600519", "moutai": "600519",
    "byd":    "002594",  # 比亚迪 A股
    "zxgjt":  "601628",  # 中国人寿
    "zgpa":   "601318",  # 中国平安
    "zgms":   "600519",
}


def _build_pinyin_index(stocks):
    """给每只股票计算：拼音首字母 + 完整拼音（无声调）"""
    try:
        from pypinyin import lazy_pinyin, Style
    except ImportError:
        return [(code, name, "", "") for code, name in stocks]

    result = []
    for code, name in stocks:
        syllables = lazy_pinyin(name, style=Style.NORMAL)
        initials  = lazy_pinyin(name, style=Style.FIRST_LETTER)
        full_py   = "".join(syllables)        # guizhoumaotai
        init_str  = "".join(initials)         # gzmt
        result.append((code, name, init_str, full_py))
    return result


def _load_cn():
    global _CN_CACHE, _PY_INDEX, _CN_LOADING
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
                    # 读拼音索引
                    if os.path.exists(_PINYIN_FILE):
                        with open(_PINYIN_FILE, encoding="utf-8") as f:
                            _PY_INDEX = [tuple(x) for x in json.load(f)]
                    else:
                        _PY_INDEX = _build_pinyin_index(_CN_CACHE)
                        _save_pinyin(_PY_INDEX)
                    return _CN_CACHE

        # 2. 缓存过期，从 AKShare 下载
        import akshare as ak
        df = ak.stock_info_a_code_name()
        cols = list(df.columns)
        rows = [(str(r[cols[0]]), str(r[cols[1]])) for _, r in df.iterrows()]
        _CN_CACHE = rows

        # 3. 写文件缓存
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)

        # 4. 重建拼音索引
        _PY_INDEX = _build_pinyin_index(rows)
        _save_pinyin(_PY_INDEX)

    except Exception:
        _CN_CACHE = _CN_CACHE or []
        _PY_INDEX = _PY_INDEX or []
    finally:
        _CN_LOADING = False
        _CN_READY.set()
    return _CN_CACHE


def _save_pinyin(index):
    try:
        with open(_PINYIN_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception:
        pass


def _load_cn_etf():
    """加载国内ETF/基金列表，缓存到 data/cn_etfs.json。"""
    global _ETF_CACHE, _ETF_LOADING
    if _ETF_CACHE is not None:
        return _ETF_CACHE
    if _ETF_LOADING:
        _ETF_READY.wait(timeout=30)
        return _ETF_CACHE or []
    _ETF_LOADING = True
    try:
        if os.path.exists(_ETF_CACHE_FILE):
            age = time.time() - os.path.getmtime(_ETF_CACHE_FILE)
            if age < _ETF_CACHE_TTL:
                with open(_ETF_CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    _ETF_CACHE = [tuple(x) for x in data]
                    return _ETF_CACHE

        import akshare as ak
        df = ak.fund_etf_spot_em()
        # 列名：代码, 名称, ...
        code_col = next((c for c in df.columns if "代码" in c or c.lower() == "code"), df.columns[0])
        name_col = next((c for c in df.columns if "名称" in c or c.lower() == "name"), df.columns[1])
        rows = [(str(r[code_col]).zfill(6), str(r[name_col])) for _, r in df.iterrows()]
        _ETF_CACHE = rows
        os.makedirs(os.path.dirname(_ETF_CACHE_FILE), exist_ok=True)
        with open(_ETF_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    except Exception:
        _ETF_CACHE = _ETF_CACHE or []
    finally:
        _ETF_LOADING = False
        _ETF_READY.set()
    return _ETF_CACHE


def _load_cn_funds():
    """加载国内全量场外基金列表（混合/股票/债券/货币等），缓存到 cn_funds.json。"""
    global _FUND_CACHE, _FUND_LOADING
    if _FUND_CACHE is not None:
        return _FUND_CACHE
    if _FUND_LOADING:
        _FUND_READY.wait(timeout=30)
        return _FUND_CACHE or []
    _FUND_LOADING = True
    try:
        if os.path.exists(_FUND_CACHE_FILE):
            age = time.time() - os.path.getmtime(_FUND_CACHE_FILE)
            if age < _FUND_CACHE_TTL:
                with open(_FUND_CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    _FUND_CACHE = [tuple(x) for x in data]
                    return _FUND_CACHE

        import akshare as ak
        df = ak.fund_name_em()
        # 列名：基金代码, 拼音缩写, 基金简称, 基金类型, 拼音全称
        rows = [(str(r["基金代码"]).zfill(6), str(r["基金简称"])) for _, r in df.iterrows()]
        _FUND_CACHE = rows
        os.makedirs(os.path.dirname(_FUND_CACHE_FILE), exist_ok=True)
        with open(_FUND_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    except Exception:
        _FUND_CACHE = _FUND_CACHE or []
    finally:
        _FUND_LOADING = False
        _FUND_READY.set()
    return _FUND_CACHE


def _prewarm():
    threading.Thread(target=_load_cn, daemon=True).start()
    threading.Thread(target=_load_cn_etf, daemon=True).start()
    threading.Thread(target=_load_cn_funds, daemon=True).start()

_prewarm()


def _make_result(code, name):
    # SH: 5xx (ETF/LOF), 6xx (stock), 9xx (B/preferred)
    # SZ: 0xx (stock), 1xx (ETF/LOF), 2xx, 3xx (growth), 4xx
    exchange = "SH" if code.startswith(("5", "6", "9")) else "SZ"
    return {
        "code":     code,
        "name":     name,
        "market":   "cn",
        "exchange": exchange,
        "currency": "CNY",
    }


def _search_cn(q: str, limit: int = 8) -> list:
    """中文名/代码子串匹配（A股 + ETF + 场外基金）

    _load_cn() 必须等待（A股数据是搜索主力，通常从文件缓存秒读）。
    ETF / 场外基金由 _prewarm() 后台加载；搜索时直接用已有缓存，
    尚未就绪则跳过，不阻塞 request thread。
    """
    _load_cn()   # 等 A股列表（通常 <100ms，文件缓存）
    q_l = q.lower()
    out = []
    seen = set()

    def _scan(source):
        for code, name in (source or []):
            if q_l in code or q_l in name.lower():
                if code not in seen:
                    seen.add(code)
                    out.append(_make_result(code, name))
                    if len(out) >= limit:
                        return True
        return False

    # Priority: A股 → 交易所 ETF → 场外基金（后两者不等待，用现有缓存）
    if _scan(_CN_CACHE):  return out
    if _scan(_ETF_CACHE): return out
    _scan(_FUND_CACHE)
    return out


def _search_pinyin(q: str, limit: int = 8) -> list:
    """拼音首字母 / 完整拼音 匹配"""
    _load_cn()
    q_l = q.lower()
    out = []
    for entry in (_PY_INDEX or []):
        code, name, initials, full_py = entry
        if q_l == initials or q_l in full_py or full_py.startswith(q_l):
            out.append(_make_result(code, name))
            if len(out) >= limit:
                break
    return out


def _search_hk_names(q: str) -> list:
    """港股中文名映射"""
    ticker = HK_NAMES.get(q.strip())
    if ticker:
        return _search_yf(ticker)
    return []


def _search_yf_name(query: str, limit: int = 6) -> list:
    """用 yfinance.Search 按公司名搜索，适合含空格或模糊的输入。只返回股票类型。"""
    cached = _cache_get(f"name:{query.lower()}")
    if cached is not None:
        return cached
    try:
        import yfinance as yf
        results = []
        for q in yf.Search(query, max_results=limit * 2).quotes:
            if q.get("quoteType") not in ("EQUITY", "ETF"):
                continue
            symbol = q.get("symbol", "")
            name   = q.get("shortname") or q.get("longname") or symbol
            exch   = q.get("exchDisp", "")
            sym_up = symbol.upper()
            if sym_up.endswith(".NZ"):
                market = "nz"
            elif sym_up.endswith(".HK"):
                market = "hk"
            elif sym_up.endswith((".KS", ".KQ")):
                market = "kr"
            elif sym_up.endswith(".AX"):
                market = "au"
            elif "." not in sym_up:
                market = "us"
            else:
                market = "other"
            if market == "other":
                continue
            results.append({"code": sym_up, "name": name, "market": market, "exchange": exch})
            if len(results) >= limit:
                break
        _cache_set(f"name:{query.lower()}", results)
        return results
    except Exception:
        return []


def _search_yf(ticker: str) -> list:
    cache_key = f"yf:{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf
        # 港股GEM代码如 08611.HK → yfinance需要 8611.HK（去前导零）
        # 主板4位代码 0981/0700.HK 保持原样，yfinance 需要完整4位
        if ticker.endswith(".HK"):
            parts = ticker.split(".")
            if len(parts[0]) >= 5:   # GEM: 5位 → 去前导零
                parts[0] = parts[0].lstrip("0") or "0"
            ticker = ".".join(parts)
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
        elif code.endswith((".KS", ".KQ")) or curr == "KRW":
            market = "kr"
        elif code.endswith(".AX") or curr == "AUD":
            market = "au"
        else:
            market = "us"
        result = [{"code": code, "name": short,
                   "market": market, "exchange": exch, "currency": curr}]
        _cache_set(cache_key, result)
        return result
    except Exception:
        _cache_set(cache_key, [])   # cache misses too, avoid hammering yfinance
        return []


def search(q: str, limit: int = 10) -> list:
    q = q.strip()
    if not q:
        return []

    seen = set()
    cn_results   = []   # A股 / 中文
    intl_results = []   # 港股 / 美股 / NZ / 韩股

    def _add_cn(items):
        for r in items:
            k = r["code"]
            if k not in seen:
                seen.add(k); cn_results.append(r)

    def _add_intl(items):
        for r in items:
            k = r["code"]
            if k not in seen:
                seen.add(k); intl_results.append(r)

    has_cn   = any('\u4e00' <= c <= '\u9fff' for c in q)
    is_num   = q.isdigit()
    has_dot  = '.' in q
    has_space = ' ' in q
    q_l      = q.lower()
    alpha    = bool(re.match(r'^[A-Za-z]', q))

    # 1. 港股中文名映射（优先，避免「腾讯」找不到）
    if has_cn:
        _add_intl(_search_hk_names(q))

    # 2. A股中文名 / 代码
    if has_cn or is_num or (not alpha and len(q) <= 7):
        _add_cn(_search_cn(q, limit=limit))

    # 3. 拼音首字母 / 拼音全拼（英文输入）
    if alpha and not has_dot:
        if q_l in PINYIN_ALIAS:
            _add_cn(_search_cn(PINYIN_ALIAS[q_l], limit=1))
        _add_cn(_search_pinyin(q_l, limit=limit))

    # 4. 国际股票搜索
    if alpha or has_dot:
        ticker = q.upper()
        if has_dot:
            # 精确代码（含后缀）：直接单个 Ticker 查询
            _add_intl(_search_yf(ticker))
        else:
            # 无后缀英文：用 yf.Search() 一次搜所有市场（比5个串行 Ticker 快4-5倍）
            _add_intl(_search_yf_name(ticker, limit=limit))

    # 4b. 纯数字：可能是韩股代码（005930 等），也尝试 .KS
    if is_num and len(q) == 6 and not cn_results:
        _add_intl(_search_yf(q + ".KS"))

    # 4c. 含空格：名称搜索已在上面统一处理，无需重复

    # 5. 兜底：什么都没找到再宽泛搜 A股
    if not cn_results and not intl_results:
        _add_cn(_search_cn(q, limit=limit))

    # 合并策略：
    # - 中文输入 → A股优先
    # - 拼音别名命中（byd/moutai）→ A股优先
    # - 其他英文 ticker → 国际优先
    pinyin_hit = alpha and not has_dot and q_l in PINYIN_ALIAS
    if has_cn or pinyin_hit:
        merged = cn_results + intl_results
    else:
        merged = intl_results + cn_results

    return merged[:limit]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "茅台"
    for item in search(query):
        print(item)
