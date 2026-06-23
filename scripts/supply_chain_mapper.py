"""
US-97 · 自动供应链溯源引擎
- 美股：从 SEC 10-K Risk Factors 提取 Tier-1 供应商
- A股：从 CNINFO 年报 PDF "主要供应商" 章节提取（需 pdfplumber）
结果统一写入 supply_chain_links 表。
"""
import json
import re
import time
from datetime import datetime, timezone, timedelta

import requests

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

from scripts.buffett_groq import _call_groq
from radar_app.data.core import get_conn, CN_TZ

# ── 常量 ──────────────────────────────────────────────────────────────────────

EDGAR_COMPANY_TICKERS = "https://data.sec.gov/submissions/{cik}.json"
EDGAR_TICKERS_JSON   = "https://www.sec.gov/files/company_tickers.json"
EDGAR_HEADERS = {"User-Agent": "PBC-StockRadar poluovoila@gmail.com"}

_CHOKEPOINT_KW = {
    # sole/single source (90-100)
    "sole source":        95,
    "single source":      90,
    "sole supplier":      95,
    "single supplier":    90,
    # limited alternatives (60-74)
    "limited alternative": 65,
    "few alternative":     62,
    "limited number of supplier": 68,
    "limited supply":      60,
    # sole qualification / no substitute (75-89)
    "no substitute":       85,
    "no qualified alternative": 82,
    "qualified supplier":  75,
    # qualified supply list (QSL) language
    "qualified vendor list": 78,
    "approved vendor":    76,
    "approved supplier":  76,
    # concentration risk
    "concentration risk":  70,
    "supplier concentration": 72,
    # geopolitical / export control
    "export control":      68,
    "export license":      65,
    "trade restriction":   65,
    "tariff":              55,
    # foundry / fab (semiconductor specific)
    "foundry":             72,
    "tsmc":                88,
    "samsung foundry":     80,
    "globalfoundries":     72,
    # rare material
    "rare earth":          80,
    "specialty gas":       72,
    "indium":              85,
    "gallium":             85,
    "germanium":           82,
}

CACHE_TTL_DAYS = 30  # 重新扫描间隔

# ── 市场推断 ──────────────────────────────────────────────────────────────────

# 日本/欧洲大厂名称关键词 → 快速判断无 ticker 时的市场归属
_JP_KEYWORDS = {
    "shin-etsu", "shinetsu", "sumco", "jsr", "tokyo ohka", "tok ", " tok",
    "kioxia", "toshiba", "tokyo electron", " tel ", "murata", "tdk",
    "kyocera", "renesas", "rohm", "nidec", "canon", "nikon",
    "ibiden", "mitsui", "mitsubishi", "hitachi", "fujitsu", "elpida",
    "air liquide japan", "showa denko",
}
_EU_KEYWORDS = {
    "asml", "infineon", "st microelectronics", "stmicro", "asm international",
    "aixtron", "suss microtec", "besi", "amsl", "siltronic",
    "merck kgaa", "basf", "air liquide",
}
_TW_KEYWORDS = {
    "tsmc", "taiwan semiconductor", "ase group", "ase technology",
    "unimicron", "nan ya", "powerchip", "mediatek", "realtek",
    "united microelectronics", "umc",
}


def _infer_market(supplier_name: str, supplier_ticker: str | None) -> str:
    """
    根据 ticker 后缀或供应商名称关键词推断所属市场。
    名称优先于 ticker，避免 ADR（KXIAY/TOELY）被误判为美股。
    返回: us / cn / jp / eu / tw / kr / au / hk / private / unknown
    """
    name_l = supplier_name.lower()
    # Name-based check first: JP/EU/TW names are never "really" US
    if any(kw in name_l for kw in _JP_KEYWORDS): return "jp"
    if any(kw in name_l for kw in _EU_KEYWORDS): return "eu"
    if any(kw in name_l for kw in _TW_KEYWORDS): return "tw"

    if supplier_ticker:
        t = supplier_ticker.upper()
        if t.endswith(".HK"):    return "hk"
        if t.endswith(".KS") or t.endswith(".KQ"): return "kr"
        if t.endswith(".AX"):    return "au"
        if t.endswith(".NZ"):    return "nz"
        if re.match(r"^\d{6}$", t): return "cn"
        if re.match(r"^[A-Z]{1,5}$", t): return "us"

    return "private"


# ── CIK 查找 ──────────────────────────────────────────────────────────────────

_cik_cache: dict[str, str] = {}


def _ticker_to_cik(ticker: str) -> str | None:
    """将美股 ticker 转换为 SEC CIK（10位，左补零）。"""
    t = ticker.upper()
    if t in _cik_cache:
        return _cik_cache[t]
    try:
        resp = requests.get(EDGAR_TICKERS_JSON, headers=EDGAR_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for v in data.values():
            if v.get("ticker", "").upper() == t:
                cik = str(v["cik_str"]).zfill(10)
                _cik_cache[t] = cik
                return cik
    except Exception as e:
        print(f"    [supply_chain] CIK lookup failed for {ticker}: {e}")
    return None


# ── 10-K 文档 URL ─────────────────────────────────────────────────────────────

def _get_latest_10k_url(cik: str) -> str | None:
    """从 submissions API 找最新 10-K 正文 URL。"""
    try:
        url = EDGAR_COMPANY_TICKERS.format(cik=f"CIK{cik}")
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        sub = resp.json()

        filings = sub.get("filings", {}).get("recent", {})
        forms  = filings.get("form", [])
        docs   = filings.get("primaryDocument", [])
        accnos = filings.get("accessionNumber", [])
        dates  = filings.get("filingDate", [])

        for i, form in enumerate(forms):
            if form in ("10-K", "10-K/A"):
                accno = accnos[i].replace("-", "")
                doc   = docs[i]
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accno}/{doc}"
                print(f"    [supply_chain] 10-K found ({dates[i]}): {url}")
                return url
    except Exception as e:
        print(f"    [supply_chain] 10-K URL lookup failed for CIK {cik}: {e}")
    return None


# ── Risk Factors 提取 ─────────────────────────────────────────────────────────

_TAG_RE = re.compile(r'<[^>]+>')

# Keywords with a priority weight — higher weight snippets sort first
# so the most specific supply chain language wins the char budget
_SUPPLY_KEYWORDS: list[tuple[str, int]] = [
    # Named companies / products (highest priority)
    ("tsmc", 10), ("taiwan semiconductor", 10), ("kioxia", 10),
    ("samsung foundry", 10), ("samsung electronics", 10),
    ("globalfoundries", 10), ("intel foundry", 10),
    ("sk hynix", 10), ("micron technology", 10),
    ("foxconn", 10), ("hon hai", 10), ("flextronics", 10), ("jabil", 10),
    ("flash venture", 10), ("applied materials", 9), ("lam research", 9),
    ("kla corporation", 9), ("tokyo electron", 9), ("asml", 9),
    # Sole/single source (very specific)
    ("sole source", 9), ("single source", 9),
    ("sole supplier", 9), ("single supplier", 9),
    ("no substitute", 8), ("no alternative", 8),
    # JV / manufacturing
    ("joint venture", 8), ("nand flash", 8), ("nand memory", 8),
    ("wafer", 7), ("3d nand", 8), ("flash memory", 7),
    ("foundry", 7), ("contract manufacturer", 7),
    # Generic risk language
    ("limited number of supplier", 7), ("limited alternative", 7),
    ("qualified supplier", 6), ("approved vendor", 6), ("approved supplier", 6),
    ("supply disruption", 6), ("supplier concentration", 6),
    ("purchase from", 5), ("procure", 5), ("rely on", 5), ("dependent on", 5),
    # Materials
    ("rare earth", 8), ("indium", 8), ("gallium", 8), ("germanium", 8),
    ("hbm", 8), ("high bandwidth memory", 8), ("cobalt", 7),
    # Equipment
    ("lithography", 7), ("fabrication", 6),
]


def _extract_supply_snippets(text: str, max_chars: int = 10000) -> str:
    """
    全文关键词搜索，按优先级权重排序后拼接，总长不超 max_chars。
    不依赖 Item 1A/1B 章节边界——对任何格式的 10-K 都能工作。
    """
    lower = text.lower()
    # Collect (weight, position, start, end, snippet)
    hits: list[tuple[int, int, str]] = []
    seen_ranges: list[tuple[int, int]] = []

    for kw, weight in _SUPPLY_KEYWORDS:
        idx = 0
        while True:
            pos = lower.find(kw, idx)
            if pos == -1:
                break
            start = max(0, pos - 300)
            end   = min(len(text), pos + 700)
            # Skip if this position was already covered
            if not any(s <= pos <= e for s, e in seen_ranges):
                seen_ranges.append((start, end))
                hits.append((weight, pos, text[start:end]))
            idx = pos + 1

    if not hits:
        return ""

    # Sort by weight desc, then position asc (named companies first, then by doc order)
    hits.sort(key=lambda h: (-h[0], h[1]))

    combined = " ... ".join(snip for _, _, snip in hits)
    return combined[:max_chars]


_PROSE_START_RE = re.compile(
    r'(?:part\s+i\b|table\s+of\s+contents|forward.looking\s+statement)',
    re.IGNORECASE,
)


def _fetch_risk_factors(doc_url: str) -> str:
    """
    下载 10-K HTML，全文关键词搜索提取供应链段落。
    跳过 XBRL 内联元数据前缀（现代 SEC 文件首 20-30K 是 XBRL，不是散文）。
    不依赖 Item 1A 章节边界正则，对任意格式的年报均有效。
    """
    try:
        import html as _html
        resp = requests.get(doc_url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        raw = resp.text

        # Strip HTML tags + decode entities (&#160; etc.)
        plain = _TAG_RE.sub(' ', raw)
        plain = _html.unescape(plain)
        plain = re.sub(r'\s+', ' ', plain)

        # Skip XBRL/metadata preamble — find where actual prose begins
        m = _PROSE_START_RE.search(plain)
        prose_start = m.start() if m else min(25000, len(plain) // 4)
        prose = plain[prose_start:]

        snippets = _extract_supply_snippets(prose, max_chars=10000)
        if snippets:
            print(f"    [supply_chain] 提取到供应链段落 {len(snippets)} chars (prose_start={prose_start})")
            return snippets

        # Fallback: first 8000 chars of prose
        return prose[:8000]
    except Exception as e:
        print(f"    [supply_chain] fetch_risk_factors failed: {e}")
    return ""


# ── LLM 提取 ─────────────────────────────────────────────────────────────────

_SYSTEM_SC = (
    "You are a supply-chain risk analyst. "
    "Given an excerpt from a 10-K filing, identify the company's critical Tier-1 suppliers "
    "or raw material sources where there is concentrated dependency. "
    "\n\nRULES — follow strictly:"
    "\n1. supplier_name MUST be a real, specific entity: a company name (e.g. 'TSMC', 'Samsung Electronics', 'Foxconn'), "
    "a named country/region source (e.g. 'Chinese rare earth suppliers', 'Taiwan-based foundries'), "
    "or a specific material (e.g. 'indium phosphide wafers', 'gallium arsenide'). "
    "\n2. NEVER use generic categories: do NOT output 'Unspecified', 'sole source suppliers', "
    "'contract manufacturers', 'third-party suppliers', 'limited number of suppliers', or any phrase "
    "that doesn't identify WHO or WHAT the dependency is on. Skip these entirely."
    "\n3. If the text mentions sole/single source risk but names no specific supplier, skip it."
    "\n4. Country/material entries ARE valid when they represent a real geographic or commodity chokepoint "
    "(e.g. 'Chinese rare earth metals', 'Taiwan semiconductor foundries')."
    "\n5. For supplier_market: use 'us' for US-listed, 'cn' for China A-share/HK, 'jp' for Japan, "
    "'eu' for Europe, 'tw' for Taiwan, 'kr' for Korea, 'private' for unlisted private companies."
    "\n\nReturn ONLY valid JSON — a list of objects with keys: "
    '"supplier_name" (string), "dependency_type" '
    '("sole_source"|"single_source"|"limited_alternatives"|"qualified_supply_list"|"concentration_risk"|"other"), '
    '"evidence_quote" (≤80 chars from the text), "is_public_company" (true|false), '
    '"supplier_market" (us|cn|jp|eu|tw|kr|private|unknown). '
    "List at most 8 entries. If no specific named dependencies found, return []."
)


def _extract_suppliers_llm(text: str, company_name: str) -> list[dict]:
    """调用 Groq LLM 从 Risk Factors 文本提取供应商列表。"""
    if not text:
        return []
    user_msg = (
        f"Company: {company_name}\n\n"
        f"Supply chain excerpts from 10-K:\n{text}\n\n"
        "Return the JSON list of critical supplier dependencies."
    )
    raw = _call_groq(_SYSTEM_SC, user_msg, max_tokens=800)
    if not raw:
        return []

    # Extract JSON array from response
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


# ── Chokepoint 评分 ──────────────────────────────────────────────────────────

def _score_chokepoint(dep: dict) -> int:
    """
    dep_type + evidence_quote 关键词打分，0-100。
    dependency_type 本身也给基础分。
    """
    base = {
        "sole_source":         92,
        "single_source":       85,
        "limited_alternatives": 65,
        "qualified_supply_list": 72,
        "concentration_risk":   60,
        "other":               40,
    }.get(dep.get("dependency_type", "other"), 40)

    quote = (dep.get("evidence_quote") or "").lower()
    bonus = max(
        (_CHOKEPOINT_KW[kw] for kw in _CHOKEPOINT_KW if kw in quote),
        default=0,
    )
    return min(100, max(base, bonus))



# ── 公共公司 ticker 查找 ──────────────────────────────────────────────────────

_REJECT_TYPES    = {"ETF", "MUTUALFUND", "CURRENCY", "FUTURE", "INDEX"}
_REJECT_SUFFIXES = (".SA", ".L", ".T", ".PA", ".DE", ".AX")
# Note: .HK, .SZ, .SS intentionally NOT rejected — we want to capture Chinese suppliers.
# yfinance returns .SS for Shanghai, .SZ for Shenzhen; we strip the suffix and use
# _lookup_cn_ticker() to get the clean 6-digit A-share code.


def _lookup_ticker(name: str) -> str | None:
    """
    用 yfinance 搜索供应商名称，返回主要交易所 ticker。
    - 美股/台股：直接返回 ticker
    - A股（.SS/.SZ）：剥离后缀，走 _lookup_cn_ticker() 匹配本地 JSON 得到6位代码
    - 港股（.HK）：保留，供 Tier-2 跳转用
    最多尝试 5 个结果，取第一个通过过滤的。
    """
    if not name:
        return None

    # 先尝试 A股本地匹配（更准确，无网络依赖）
    cn_code = _lookup_cn_ticker(name)
    if cn_code:
        return cn_code

    try:
        import yfinance as yf
        results = yf.Search(name, max_results=5)
        for q in (results.quotes or []):
            ticker    = q.get("symbol") or q.get("ticker") or ""
            type_hint = (q.get("typeDisp") or q.get("quoteType") or "").upper()
            if not ticker:
                continue
            if type_hint in _REJECT_TYPES:
                continue
            if any(ticker.upper().endswith(s) for s in _REJECT_SUFFIXES):
                continue
            # A股：yfinance 返回 600519.SS 或 000858.SZ → 转为6位代码
            if ticker.upper().endswith(".SS") or ticker.upper().endswith(".SZ"):
                bare = ticker.split(".")[0]
                if bare.isdigit() and len(bare) == 6:
                    return bare
                continue
            return ticker
    except Exception:
        pass
    return None


# ── 扫描日志（区分"还在跑"和"跑完了但没结果"）─────────────────────────────────

def _log_scan_complete(ticker: str, result_count: int, source: str = "sec_10k", note: str = "") -> None:
    """记录扫描完成时间，哪怕结果为空。"""
    from datetime import datetime
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO supply_chain_scan_log (ticker, scanned_at, result_count, source, note)
            VALUES (:ticker, :now, :cnt, :src, :note)
            ON CONFLICT(ticker) DO UPDATE SET
                scanned_at   = excluded.scanned_at,
                result_count = excluded.result_count,
                source       = excluded.source,
                note         = excluded.note
            """,
            {"ticker": ticker, "now": now, "cnt": result_count, "src": source, "note": note},
        )


def was_scan_attempted(ticker: str) -> bool:
    """返回该 ticker 是否已做过扫描（结果可能为空）。"""
    ticker = ticker.upper().split(".")[0]
    with get_conn() as c:
        row = c.execute(
            "SELECT id FROM supply_chain_scan_log WHERE ticker = :ticker",
            {"ticker": ticker},
        ).fetchone()
    return row is not None


# ── LLM 知识兜底扫描（当无公开年报时） ─────────────────────────────────────────

_SYSTEM_US_LLM = (
    "You are a supply-chain risk analyst. Based on your training knowledge, "
    "list the key upstream suppliers of the given company. "
    "Focus on: sole-source components, specialized materials, critical contract manufacturers, "
    "joint venture manufacturing partners. Include equipment suppliers and materials suppliers "
    "if they represent concentration risk. "
    "Return ONLY valid JSON — a list (max 10 items) with keys: "
    '"supplier_name" (real company name, not generic), '
    '"dependency_type" (one of: sole_source, single_source, limited_alternatives, '
    "qualified_supply_list, concentration_risk, jv_partner, other), "
    '"chokepoint_score" (0-100: 80+ = very high risk, 50 = unknown), '
    '"evidence_quote" (≤80 chars — what this supplier provides), '
    '"is_public_company" (true|false), '
    '"supplier_market" (us|cn|jp|eu|tw|kr|private|unknown — stock market where this supplier is listed, or private if unlisted). '
    "Skip vague entries like 'various suppliers'. "
    "Return [] if you have no reliable knowledge of this company's supply chain."
)


def _us_llm_fallback_scan(ticker: str, company_name: str, now: str) -> list:
    """当 SEC EDGAR 无记录时（私营/新上市/海外公司），用 LLM 知识兜底。"""
    user_msg = (
        f"Company: {company_name or ticker} (Ticker: {ticker})\n\n"
        "List the known key upstream suppliers or critical dependencies for this company."
    )
    raw = _call_groq(_SYSTEM_US_LLM, user_msg, max_tokens=700)
    m = re.search(r'\[.*\]', raw or "", re.DOTALL)
    if not m:
        return []
    try:
        suppliers = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []

    _generic = {"unspecified", "unknown", "various suppliers", "contract manufacturers",
                "third-party suppliers", "multiple suppliers"}
    links = []
    for dep in suppliers:
        name = (dep.get("supplier_name") or "").strip()
        if not name or name.lower() in _generic or len(name) < 4:
            continue
        score = int(dep.get("chokepoint_score") or 50)
        score = max(0, min(100, score))
        sup_ticker = None
        if dep.get("is_public_company"):
            sup_ticker = _lookup_ticker(name)
            time.sleep(0.2)
        market = _infer_market(name, sup_ticker) or dep.get("supplier_market", "unknown")
        links.append({
            "downstream_code":  ticker,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  dep.get("dependency_type", "other"),
            "chokepoint_score": score,
            "evidence_quote":   (dep.get("evidence_quote") or "")[:80],
            "scanned_at":       now,
            "source":           "llm_knowledge",
            "supplier_market":  market,
        })
    print(f"    [supply_chain] LLM 知识兜底提取 {len(links)} 个供应商")
    return links


# ── 主扫描函数 ────────────────────────────────────────────────────────────────

def run_supply_chain_scan(ticker: str, company_name: str = "") -> dict:
    """
    全流程：SEC → 10-K → LLM 提取 → 打分 → 写库。
    无 SEC 记录时（私营/新上市）降级到 LLM 知识兜底。
    返回 {"ok": bool, "links": [...], "error": str|None}
    """
    ticker = ticker.upper().split(".")[0]
    print(f"[supply_chain] 开始扫描 {ticker}")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # 1. CIK — 私营/非上市公司 EDGAR 找不到，降级到 LLM 知识兜底
    cik = _ticker_to_cik(ticker)
    if not cik:
        print(f"    [supply_chain] {ticker} 无 SEC EDGAR 记录，降级到 LLM 知识兜底")
        links = _us_llm_fallback_scan(ticker, company_name, now)
        if links:
            _save_links(ticker, links)
        _log_scan_complete(ticker, len(links), "llm_knowledge",
                           note="no SEC EDGAR record")
        return {"ok": bool(links), "links": links,
                "error": None if links else "no SEC filing, LLM also returned no data"}

    # 2. 10-K URL
    doc_url = _get_latest_10k_url(cik)
    if not doc_url:
        print(f"    [supply_chain] {ticker} 找到 CIK 但无 10-K 文件，降级 LLM")
        links = _us_llm_fallback_scan(ticker, company_name, now)
        if links:
            _save_links(ticker, links)
        _log_scan_complete(ticker, len(links), "llm_knowledge",
                           note="CIK found but no 10-K")
        return {"ok": bool(links), "links": links,
                "error": None if links else "No 10-K filing found"}

    # 3. Risk Factors text
    rf_text = _fetch_risk_factors(doc_url)
    if not rf_text:
        _log_scan_complete(ticker, 0, "sec_10k", note="could not extract text")
        return {"ok": False, "links": [], "error": "Could not extract Risk Factors"}

    # 4. LLM extraction
    suppliers = _extract_suppliers_llm(rf_text, company_name or ticker)
    print(f"    [supply_chain] LLM 提取到 {len(suppliers)} 个供应商")

    # 5. Score + ticker lookup
    links = []
    for dep in suppliers:
        name = dep.get("supplier_name", "").strip()
        if not name:
            continue
        # Filter out generic/unnamed entries that slipped past the LLM prompt
        _generic = {"unspecified", "unknown", "sole source suppliers",
                    "contract manufacturers", "third-party suppliers",
                    "independent contract manufacturers", "limited number of suppliers"}
        if name.lower() in _generic or len(name) < 4:
            continue
        score = _score_chokepoint(dep)
        sup_ticker = None
        if dep.get("is_public_company"):
            sup_ticker = _lookup_ticker(name)
            time.sleep(0.3)  # yfinance rate limit courtesy
        market = _infer_market(name, sup_ticker) or dep.get("supplier_market", "unknown")

        link = {
            "downstream_code":  ticker,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  dep.get("dependency_type", "other"),
            "chokepoint_score": score,
            "evidence_quote":   (dep.get("evidence_quote") or "")[:80],
            "scanned_at":       now,
            "source":           "sec_10k",
            "supplier_market":  market,
        }
        links.append(link)

    # 6. If 10-K text didn't yield named suppliers, fall back to LLM knowledge
    if not links:
        print(f"    [supply_chain] 10-K 未找到具名供应商，降级到 LLM 知识兜底")
        links = _us_llm_fallback_scan(ticker, company_name, now)
        if links:
            _save_links(ticker, links)
        _log_scan_complete(ticker, len(links), "llm_knowledge",
                           note="10-K had no named suppliers; used LLM knowledge")
        return {"ok": bool(links), "links": links, "error": None}

    _save_links(ticker, links)
    _log_scan_complete(ticker, len(links), "sec_10k")
    return {"ok": True, "links": links, "error": None}


def _save_links(downstream_code: str, links: list[dict]) -> None:
    """
    Upsert Tier-1 supply chain links.
    只在新扫描结果 >= 旧结果条数时才全量替换，防止 LLM 限速导致数据缩水。
    """
    with get_conn() as c:
        existing = c.execute(
            "SELECT COUNT(*) FROM supply_chain_links WHERE downstream_code=:code AND (hop_depth IS NULL OR hop_depth=1)",
            {"code": downstream_code},
        ).fetchone()[0]
        if len(links) < existing:
            print(f"    [supply_chain] 新结果({len(links)}) < 旧结果({existing})，保留旧数据跳过写入")
            return
        c.execute(
            "DELETE FROM supply_chain_links WHERE downstream_code=:code AND (hop_depth IS NULL OR hop_depth=1)",
            {"code": downstream_code},
        )
        for lnk in links:
            c.execute(
                """
                INSERT INTO supply_chain_links
                  (downstream_code, supplier_name, supplier_ticker,
                   dependency_type, chokepoint_score, evidence_quote,
                   scanned_at, source, hop_depth, upstream_path, tier1_code,
                   supplier_market)
                VALUES
                  (:downstream_code, :supplier_name, :supplier_ticker,
                   :dependency_type, :chokepoint_score, :evidence_quote,
                   :scanned_at, :source,
                   :hop_depth, :upstream_path, :tier1_code,
                   :supplier_market)
                """,
                {
                    **lnk,
                    "hop_depth":      lnk.get("hop_depth", 1),
                    "upstream_path":  lnk.get("upstream_path"),
                    "tier1_code":     lnk.get("tier1_code"),
                    "supplier_market": lnk.get("supplier_market", "unknown"),
                },
            )
    print(f"    [supply_chain] 写入 {len(links)} 条 supply_chain_links (hop={links[0].get('hop_depth',1) if links else '-'})")


def get_supply_chain_links(ticker: str) -> list[dict]:
    """读取该 ticker 的所有供应链链接（含多跳），按 hop_depth ASC, score DESC。"""
    ticker = ticker.upper().split(".")[0]
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT supplier_name, supplier_ticker, dependency_type,
                   chokepoint_score, evidence_quote, scanned_at, source,
                   COALESCE(hop_depth, 1) AS hop_depth,
                   upstream_path, tier1_code,
                   COALESCE(supplier_market, 'unknown') AS supplier_market
            FROM   supply_chain_links
            WHERE  downstream_code = :code
            ORDER BY COALESCE(hop_depth,1) ASC, chokepoint_score DESC
            """,
            {"code": ticker},
        ).fetchall()
    return [dict(r) for r in rows]


def _get_tier1_links_for_hop2(sup_ticker: str, sup_name: str) -> list[dict]:
    """
    Tier-2 用：取 sup_ticker 自身已缓存的 Tier-1 供应商。
    6位纯数字 ticker → A股 CNINFO 路径；其余 → SEC 路径。
    """
    cached = get_supply_chain_links(sup_ticker)
    if cached:
        print(f"    [supply_chain] Tier-2 复用缓存: {sup_ticker} ({len(cached)} 条)")
        return [r for r in cached if r.get("hop_depth", 1) == 1]

    print(f"    [supply_chain] Tier-2 扫描: {sup_ticker}")
    if sup_ticker.isdigit() and len(sup_ticker) == 6:
        result = run_cn_supply_chain_scan(sup_ticker, sup_name)
    else:
        result = run_supply_chain_scan(sup_ticker, sup_name)
    return result.get("links", [])


def is_cache_fresh(ticker: str) -> bool:
    """检查最近一次扫描（任意 hop）是否在 CACHE_TTL_DAYS 以内。"""
    ticker = ticker.upper().split(".")[0]
    with get_conn() as c:
        row = c.execute(
            "SELECT scanned_at FROM supply_chain_links "
            "WHERE downstream_code = :code ORDER BY scanned_at DESC LIMIT 1",
            {"code": ticker},
        ).fetchone()
    if not row:
        return False
    try:
        scanned = datetime.fromisoformat(row["scanned_at"])
        if scanned.tzinfo is None:
            scanned = scanned.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - scanned).days < CACHE_TTL_DAYS
    except Exception:
        return False


# ── US-101 多跳 BOM 溯源 ──────────────────────────────────────────────────────

_MAX_T1_FOR_HOP2_US = 5  # 美股：最多追踪 5 个 Tier-1（SEC HTTP 较快）
_MAX_T1_FOR_HOP2_CN = 3  # A股：最多追踪 3 个 Tier-1（PDF 下载慢）


def run_multihop_scan(ticker: str, market: str, company_name: str = "", max_depth: int = 2) -> dict:
    """
    多跳 BOM 溯源（美股 + A股均支持）。
    - Hop 1：run_supply_chain_scan_auto（SEC 10-K / CNINFO PDF）
    - Hop 2：对有 ticker 的 Tier-1 获取其上游供应商
      美股：走 SEC 路径；A股供应商（6位数字）：走 CNINFO 路径
    """
    ticker = ticker.upper().split(".")[0]
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    max_t1 = _MAX_T1_FOR_HOP2_CN if market == "cn" else _MAX_T1_FOR_HOP2_US

    # ── Hop 1 ─────────────────────────────────────────────────────────────────
    r1 = run_supply_chain_scan_auto(ticker, market, company_name)
    tier1_links = r1.get("links", [])

    for lnk in tier1_links:
        lnk["hop_depth"]     = 1
        lnk["upstream_path"] = json.dumps([ticker])
        lnk["tier1_code"]    = None

    if not tier1_links or max_depth < 2:
        return r1

    # ── Hop 2 ─────────────────────────────────────────────────────────────────
    t1_with_ticker = [l for l in tier1_links if l.get("supplier_ticker")][:max_t1]

    # 预建 Tier-1 名称集合，避免循环内重复计算
    t1_names   = {l["supplier_name"] for l in tier1_links}
    t1_tickers = {(l.get("supplier_ticker") or "").upper() for l in tier1_links}

    tier2_all: list[dict] = []
    for t1 in t1_with_ticker:
        sup_ticker = t1["supplier_ticker"]
        sup_name   = t1["supplier_name"]
        try:
            t2_raw = _get_tier1_links_for_hop2(sup_ticker, sup_name)
        except Exception as e:
            print(f"    [supply_chain] Hop-2 failed for {sup_ticker}: {e}")
            continue

        for lnk in t2_raw:
            # 跳过循环引用 + 已是 Tier-1 的节点
            sup2_ticker = (lnk.get("supplier_ticker") or "").upper()
            if sup2_ticker == ticker or sup2_ticker in t1_tickers:
                continue
            if lnk.get("supplier_name") in t1_names:
                continue

            t2_name   = lnk["supplier_name"]
            t2_ticker = lnk.get("supplier_ticker")
            t2_market = lnk.get("supplier_market") or _infer_market(t2_name, t2_ticker)
            tier2_all.append({
                "downstream_code":  ticker,
                "supplier_name":    t2_name,
                "supplier_ticker":  t2_ticker,
                "dependency_type":  lnk.get("dependency_type", "other"),
                "chokepoint_score": lnk.get("chokepoint_score", 40),
                "evidence_quote":   lnk.get("evidence_quote", ""),
                "scanned_at":       now,
                "source":           lnk.get("source", "cninfo_annual" if market == "cn" else "sec_10k"),
                "hop_depth":        2,
                "upstream_path":    json.dumps([ticker, sup_ticker]),
                "tier1_code":       sup_ticker,
                "supplier_market":  t2_market,
            })

    if tier2_all:
        # DELETE old Tier-2 rows, then insert new
        with get_conn() as c:
            c.execute(
                "DELETE FROM supply_chain_links WHERE downstream_code=:code AND hop_depth=2",
                {"code": ticker},
            )
            for lnk in tier2_all:
                c.execute(
                    """
                    INSERT INTO supply_chain_links
                      (downstream_code, supplier_name, supplier_ticker,
                       dependency_type, chokepoint_score, evidence_quote,
                       scanned_at, source, hop_depth, upstream_path, tier1_code,
                       supplier_market)
                    VALUES
                      (:downstream_code, :supplier_name, :supplier_ticker,
                       :dependency_type, :chokepoint_score, :evidence_quote,
                       :scanned_at, :source, :hop_depth, :upstream_path, :tier1_code,
                       :supplier_market)
                    """,
                    lnk,
                )
        print(f"    [supply_chain] 写入 {len(tier2_all)} 条 Tier-2 links for {ticker}")

    all_links = tier1_links + tier2_all
    return {"ok": True, "links": all_links, "error": None}


def get_supply_chain_tree(ticker: str) -> dict:
    """
    返回树结构，供前端分层渲染。
    {
      "tier1": [ {...link} ],
      "tier2_by_t1": { "TSMC": [ {...link} ], ... }
    }
    """
    all_links = get_supply_chain_links(ticker)
    tier1 = [l for l in all_links if l.get("hop_depth", 1) == 1]
    tier2 = [l for l in all_links if l.get("hop_depth", 1) == 2]

    tier2_by_t1: dict[str, list] = {}
    for lnk in tier2:
        t1 = lnk.get("tier1_code") or "unknown"
        tier2_by_t1.setdefault(t1, []).append(lnk)

    return {"tier1": tier1, "tier2_by_t1": tier2_by_t1}


# ══════════════════════════════════════════════════════════════════════════════
# A 股路径：CNINFO 年报 PDF → pdfplumber → Groq LLM
# ══════════════════════════════════════════════════════════════════════════════

CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://www.cninfo.com.cn/",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

_CN_SUPPLIER_KW = [
    "供应商", "采购", "主要供应商", "前五名供应商", "采购金额", "采购比例",
    "占年度采购", "供货方", "材料供应",
]

_SYSTEM_CN_SC = (
    "你是供应链风险分析师，分析A股上市公司年报。"
    "给定年报文本（可能包含：主要供应商表、关联方采购交易、原料采购情况等），"
    "按以下优先级提取供应商信息，至少返回1条：\n"
    "1【最高优先】前五名供应商明细表：提取每个供应商名称 + 采购占比%；\n"
    "2【次优先】关联方交易中的「购买商品」采购对手方（提取公司全名 + 金额）；\n"
    "3【兜底】若只有前五名供应商的汇总数字（如「前五名供应商占年度采购总额25.7%」），"
    "仍要创建一条entry，supplier_name 设为「前五名供应商（合计）」，purchase_ratio 设为该百分比；\n"
    "4 若有原料类别采购金额表（如包装材料/原材料），也可提取类别名称作为供应商条目。\n\n"
    "返回合法 JSON 列表，每个对象含：\n"
    "supplier_name（名称），purchase_ratio（采购占比%，无则null），"
    "evidence_quote（原文引用 ≤80字），is_listed（是否上市，true/false）。\n"
    "最多8条。不要返回任何JSON之外的文字。"
)


_SYSTEM_CN_SC_LLM = (
    "你是供应链风险分析师，专注A股上市公司。"
    "根据你的训练数据，列出该公司已知的主要上游供应商。"
    "返回合法 JSON 列表，每个对象含：\n"
    "supplier_name（供应商名称），purchase_ratio（已知采购占比%，无则null），"
    "evidence_quote（你的依据，≤80字，注明\"基于公开信息\"），is_listed（是否A股/港股/美股上市，true/false）。\n"
    "最多6条，只列你有信心的条目。不要返回任何JSON之外的文字。"
)


def _cn_llm_fallback_scan(code: str, company_name: str, now: str) -> list:
    """当 CNINFO 不可达时，用 Groq 训练数据作 A股供应链 fallback。"""
    user_msg = (
        f"公司：{company_name}（A股代码：{code}）\n\n"
        "请根据你已知的公开信息，列出该公司主要上游供应商。"
    )
    raw = _call_groq(_SYSTEM_CN_SC_LLM, user_msg, max_tokens=600)
    m = re.search(r'\[.*\]', raw or "", re.DOTALL)
    if not m:
        return []
    try:
        suppliers = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    links = []
    for s in suppliers:
        name = (s.get("supplier_name") or "").strip()
        if not name:
            continue
        ratio = s.get("purchase_ratio")
        try:
            ratio = float(ratio) if ratio is not None else None
        except (TypeError, ValueError):
            ratio = None
        sup_ticker = None
        if s.get("is_listed"):
            sup_ticker = _lookup_cn_ticker(name)
            time.sleep(0.2)
        links.append({
            "downstream_code":  code,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  "concentration_risk" if (ratio and ratio >= 30) else "other",
            "chokepoint_score": _score_cn_chokepoint(ratio),
            "evidence_quote":   (s.get("evidence_quote") or "基于公开信息")[:80],
            "scanned_at":       now,
            "source":           "llm_knowledge",
        })
    print(f"    [supply_chain_cn] LLM fallback 提取到 {len(links)} 个供应商")
    return links


_EM_ANN_URL  = "https://np-anotice-stock.eastmoney.com/api/security/ann"
_EM_CONT_URL = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
_EM_HEADERS  = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"}

# 年报正文标题特征：\d{4}年年度报告（全文/正文）结尾，或仅"年度报告"结尾
_CN_ANNUAL_RE = re.compile(r'\d{4}年年度报告(全文|正文|（草案）)?$')
# 非年报公告关键词（命中即排除）
_CN_ANNUAL_EXCLUDE = ("英文", "摘要", "更正", "H股", "港股", "半年度",
                      "说明会", "业绩会", "征集", "网上", "预约", "提示性公告")


def _get_cn_annual_report_pdf_url(code: str) -> str | None:
    """
    通过东方财富公告API获取A股最新年报 PDF 下载 URL。
    不依赖 www.cninfo.com.cn（Fly.io 上 DNS 不可达）。
    流程：
    1. np-anotice-stock.eastmoney.com → 分页查找最新年报 art_code
    2. np-cnotice-stock.eastmoney.com → 从内容API提取 pdf.dfcfw.com URL
    """
    code = code.zfill(6)
    org_pfx = "gssh" if code.startswith(("6", "9")) else "gssz"
    stock_list = f"{code},{org_pfx}{code}"

    art_code: str | None = None
    try:
        for page in range(1, 6):          # 最多翻5页，每页50条
            r = requests.get(
                _EM_ANN_URL,
                params={"sr": -1, "page_size": 50, "page_index": page,
                        "ann_type": "A", "client_source": "web",
                        "stock_list": stock_list, "f_node": 0, "s_node": 0},
                headers=_EM_HEADERS,
                timeout=15,
            )
            items = r.json().get("data", {}).get("list", [])
            if not items:
                break
            for item in items:
                title = (item.get("title_ch") or item.get("title") or "")
                # 去掉公司名前缀（"贵州茅台:2025年年度报告" → "2025年年度报告"）
                bare = title.split(":")[-1].strip()
                if any(kw in bare for kw in _CN_ANNUAL_EXCLUDE):
                    continue
                if _CN_ANNUAL_RE.search(bare):
                    art_code = item.get("art_code", "")
                    print(f"    [supply_chain_cn] 年报: {title[:50]} | {art_code}")
                    break
            if art_code:
                break
            # 当前页最旧一条超过3年前，不用再翻
            oldest_year = (items[-1].get("notice_date") or "2000")[:4]
            if int(oldest_year) < (datetime.now().year - 3):
                break
    except Exception as e:
        print(f"    [supply_chain_cn] Eastmoney ann lookup failed: {e}")
        return None

    if not art_code:
        print(f"    [supply_chain_cn] {code} 未找到年报公告")
        return None

    # Step 2: get PDF URL from content API
    try:
        r2 = requests.get(
            _EM_CONT_URL,
            params={"art_code": art_code, "client_source": "web", "page_index": 1},
            headers=_EM_HEADERS,
            timeout=10,
        )
        pdf_urls = re.findall(
            r"https://pdf\.dfcfw\.com/pdf/[^\s\"'\\]+\.pdf", r2.text, re.I
        )
        if pdf_urls:
            return pdf_urls[0].split("?")[0]   # strip timestamp query param
        # Fallback: construct from art_code (format: AN{YYYYMMDD}{id})
        return f"https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf"
    except Exception as e:
        print(f"    [supply_chain_cn] PDF URL lookup failed: {e}")
        return None


_CN_SUPPLIER_STRONG_KW = [
    "前五名供应商", "前五名原材料供应商", "前5名供应商",
    "供应商名称", "供应商1", "供应商一",
    "主要供应商情况", "公司主要供应商",
]
_CN_RELATED_SUPPLIER_KW = ["购买商品", "采购", "关联采购"]


def _fetch_cn_supplier_text(pdf_url: str) -> str:
    """
    下载年报 PDF，分三优先级提取供应链相关页面（最多 6000 字符）：
    1. 「前五名供应商」明细页 + 下一页（供应商名称表格）
    2. 关联方采购页（购买商品/接受劳务中含有具体公司名的行）
    3. 一般「采购」页（fallback）
    """
    try:
        import pdfplumber, io
        # Use EM_HEADERS: pdf.dfcfw.com and static.cninfo.com.cn both accept these
        pdf_headers = {**_EM_HEADERS, "Referer": "https://www.eastmoney.com/"}
        resp = requests.get(pdf_url, headers=pdf_headers, timeout=40)
        resp.raise_for_status()

        pages_text: list[tuple[int, str]] = []  # (page_idx, text)
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            all_pages = [(i, page.extract_text() or "") for i, page in enumerate(pdf.pages)]

        # Priority 1: pages with strong supplier keywords (+ next page)
        strong_idx: set[int] = set()
        for i, text in all_pages:
            if any(kw in text for kw in _CN_SUPPLIER_STRONG_KW):
                strong_idx.add(i)
                strong_idx.add(i + 1)  # usually contains the actual name table

        # Priority 2: related-party transaction pages (typically pages 30-55 in annual reports)
        related_idx: set[int] = set()
        for i, text in all_pages:
            if i < 25 or i > 80:
                continue
            if "购买商品" in text and ("万元" in text or "亿元" in text):
                related_idx.add(i)

        # Priority 3: general supplier/procurement pages
        general_idx: set[int] = set()
        for i, text in all_pages:
            if any(kw in text for kw in _CN_SUPPLIER_KW):
                general_idx.add(i)

        ordered = (
            [all_pages[i][1] for i in sorted(strong_idx)  if i < len(all_pages)] +
            [all_pages[i][1] for i in sorted(related_idx - strong_idx) if i < len(all_pages)] +
            [all_pages[i][1] for i in sorted(general_idx - strong_idx - related_idx) if i < len(all_pages)]
        )

        # Limit total
        combined = "\n\n".join(ordered[:8])
        if not combined.strip():
            return ""
        n_pages = min(len(ordered), 8)
        print(f"    [supply_chain_cn] 提取到 {n_pages} 页供应链内容，{len(combined)} chars")
        return combined[:6000]
    except ImportError:
        print("    [supply_chain_cn] pdfplumber 未安装，无法解析年报 PDF")
    except Exception as e:
        print(f"    [supply_chain_cn] PDF 提取失败: {e}")
    return ""


def _score_cn_chokepoint(ratio: float | None) -> int:
    """
    A股按采购占比打集中度风险分（0-100）。
    占比越高，依赖越深，风险分越高。
    """
    if ratio is None:
        return 50  # 无数据时给中等分
    if ratio >= 50:
        return 92
    if ratio >= 30:
        return 80
    if ratio >= 20:
        return 68
    if ratio >= 10:
        return 55
    return 40


def _lookup_cn_ticker(name: str) -> str | None:
    """搜索供应商是否为A股上市公司，返回股票代码。优先用本地 JSON，无网络依赖。"""
    if not name:
        return None
    name = name.strip().replace(" ", "")
    try:
        import json, os, re
        _path = os.path.join(os.path.dirname(__file__), "../data/cn_stocks.json")
        stocks = json.load(open(_path))
        # 精确匹配
        for code, sname in stocks:
            if sname.replace(" ", "") == name:
                return code
        # 包含匹配
        for code, sname in stocks:
            s = sname.replace(" ", "")
            if name in s or s in name:
                return code
        # 去掉常见后缀再匹配（处理改名、旧名），root 至少 3 字避免过度匹配
        root = re.sub(r'(股份|集团|控股|科技|新能源|能源|实业|有限公司|公司)$', '', name)
        if root and root != name and len(root) >= 3:
            for code, sname in stocks:
                s = sname.replace(" ", "")
                if root in s:
                    return code
    except Exception:
        pass
    return None


def run_cn_supply_chain_scan(code: str, company_name: str = "") -> dict:
    """
    A股供应链扫描：东方财富年报 PDF（pdf.dfcfw.com）→ pdfplumber → Groq LLM。
    不再依赖 www.cninfo.com.cn（Fly.io Sydney 上 DNS 不可达）。
    code: 6位A股代码（如 '600519'）
    """
    code = code.zfill(6)
    print(f"[supply_chain_cn] 开始扫描 A股 {code}")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # 1. 获取年报 PDF URL（东方财富公告API，全球可达）
    pdf_url = _get_cn_annual_report_pdf_url(code)
    if not pdf_url:
        print(f"    [supply_chain_cn] 未找到年报PDF，降级为 LLM 知识扫描")
        links = _cn_llm_fallback_scan(code, company_name, now)
        if links:
            _save_links(code, links)
        return {"ok": bool(links), "links": links, "error": None if links else "LLM 未返回数据"}

    print(f"    [supply_chain_cn] 东财年报 PDF: {pdf_url}")

    # 2. 提取供应商文本
    text = _fetch_cn_supplier_text(pdf_url)
    if not text:
        return {"ok": False, "links": [], "error": "未能提取供应商文本"}

    # 3. LLM 提取
    user_msg = (
        f"公司：{company_name or code}\n\n"
        f"年报供应商相关内容：\n{text}\n\n"
        "请提取主要供应商信息，返回JSON列表。"
    )
    raw = _call_groq(_SYSTEM_CN_SC, user_msg, max_tokens=800)
    m = re.search(r'\[.*\]', raw or "", re.DOTALL)
    suppliers = []
    if m:
        try:
            suppliers = json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    print(f"    [supply_chain_cn] LLM 提取到 {len(suppliers)} 个供应商")

    # 4. 打分 + 查 ticker + 写库
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    links = []
    for s in suppliers:
        name = (s.get("supplier_name") or "").strip()
        if not name:
            continue
        ratio = s.get("purchase_ratio")
        try:
            ratio = float(ratio) if ratio is not None else None
        except (TypeError, ValueError):
            ratio = None

        score = _score_cn_chokepoint(ratio)
        sup_ticker = None
        if s.get("is_listed"):
            sup_ticker = _lookup_cn_ticker(name)
            time.sleep(0.2)

        market = _infer_market(name, sup_ticker) if sup_ticker else "cn"
        links.append({
            "downstream_code":  code,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  "concentration_risk" if (ratio and ratio >= 30) else "other",
            "chokepoint_score": score,
            "evidence_quote":   (s.get("evidence_quote") or "")[:80],
            "scanned_at":       now,
            "source":           "cninfo_annual",
            "supplier_market":  market,
        })

    if links:
        _save_links(code, links)

    return {"ok": True, "links": links, "error": None}


def run_supply_chain_scan_auto(code: str, market: str, company_name: str = "") -> dict:
    """
    自动路由：A股走东方财富年报PDF，美股走 SEC 10-K。
    """
    if market == "cn":
        return run_cn_supply_chain_scan(code, company_name)
    else:
        # US/HK/NZ 等走原 SEC 路径（HK/NZ无EDGAR，会返回 CIK not found）
        return run_supply_chain_scan(code, company_name)
