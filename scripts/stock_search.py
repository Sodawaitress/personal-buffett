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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_CACHE_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "cn_stocks.json")
_PINYIN_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cn_stocks_pinyin.json")
_CACHE_TTL   = 604800  # 7 天（A股列表变化极慢）

_CN_CACHE    = None   # [(code, name), ...]
_PY_INDEX    = None   # [(code, name, initials, full_pinyin), ...]
_CN_LOADING  = False
_CN_READY    = threading.Event()

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


def _prewarm():
    threading.Thread(target=_load_cn, daemon=True).start()

_prewarm()


def _make_result(code, name):
    return {
        "code":     code,
        "name":     name,
        "market":   "cn",
        "exchange": "SH" if code.startswith(("6", "9")) else "SZ",
        "currency": "CNY",
    }


def _search_cn(q: str, limit: int = 8) -> list:
    """中文名/代码子串匹配"""
    _load_cn()
    q_l = q.lower()
    out = []
    for code, name in (_CN_CACHE or []):
        if q_l in code or q_l in name.lower():
            out.append(_make_result(code, name))
            if len(out) >= limit:
                break
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


def _search_yf(ticker: str) -> list:
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
            k = r["code"]
            if k not in seen:
                seen.add(k)
                results.append(r)

    has_cn  = any('\u4e00' <= c <= '\u9fff' for c in q)
    is_num  = q.isdigit()
    has_dot = '.' in q
    q_l     = q.lower()
    alpha   = bool(re.match(r'^[A-Za-z]', q))

    # 1. 港股中文名映射（优先，避免「腾讯」找不到）
    if has_cn:
        _add(_search_hk_names(q))

    # 2. A股中文名 / 代码
    if has_cn or is_num or (not alpha and len(q) <= 7):
        _add(_search_cn(q, limit=limit))

    # 3. 拼音首字母 / 拼音全拼（英文输入）
    if alpha and not has_dot:
        # 固定别名（byd → 002594）
        if q_l in PINYIN_ALIAS:
            code = PINYIN_ALIAS[q_l]
            _add(_search_cn(code, limit=1))
        # 拼音索引
        _add(_search_pinyin(q_l, limit=limit))

    # 4. yfinance Ticker（英文 / 带点）
    if alpha or has_dot:
        ticker = q.upper()
        # 如果已经从拼音找到 A 股结果，跳过同名美股误判
        # （除非明确带 .HK/.NZ/.US 后缀）
        if has_dot or not results:
            _add(_search_yf(ticker))
        if not has_dot and len(results) < limit:
            for sfx in (".HK", ".NZ", ".KS"):
                if len(results) < limit:
                    _add(_search_yf(ticker + sfx))

    # 5. 兜底：什么都没找到再宽泛搜 A股
    if not results:
        _add(_search_cn(q, limit=limit))

    return results[:limit]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "茅台"
    for item in search(query):
        print(item)
