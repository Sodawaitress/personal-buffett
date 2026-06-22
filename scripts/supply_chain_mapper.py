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

_ITEM_1A_RE = re.compile(
    r'(?:item\s+1a[\.\s]*risk\s+factors)(.*?)(?:item\s+1b|item\s+2)',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r'<[^>]+>')


_SUPPLY_KEYWORDS = [
    # Sole/single source
    "sole source", "single source", "single supplier", "sole supplier",
    "no alternative", "no substitute",
    # Named foundries / manufacturers
    "tsmc", "taiwan semiconductor", "samsung foundry", "samsung electronics",
    "globalfoundries", "intel foundry", "sk hynix", "micron technology",
    "foxconn", "hon hai", "flextronics", "jabil",
    # Generic supply chain risk language
    "foundry", "contract manufacturer", "outsource", "third-party manufacturer",
    "limited number of supplier", "limited alternative",
    "qualified supplier", "approved vendor", "approved supplier",
    "supply disruption", "supplier concentration",
    "purchase from", "procure", "rely on", "dependent on",
    # Materials
    "rare earth", "indium", "gallium", "germanium",
    "memory", "hbm", "high bandwidth memory", "cobalt",
]

_ITEM_1_RE = re.compile(
    r'item\s+1[\.\s]*business(.*?)item\s+1a',
    re.IGNORECASE | re.DOTALL,
)


def _extract_supply_snippets(text: str, max_chars: int = 8000) -> str:
    """在文本中按关键词定位段落，返回拼接片段（最多 max_chars）。"""
    lower = text.lower()
    seen_ranges: list[tuple[int, int]] = []
    snippets: list[str] = []

    for kw in _SUPPLY_KEYWORDS:
        idx = 0
        while True:
            pos = lower.find(kw, idx)
            if pos == -1:
                break
            start = max(0, pos - 400)
            end   = min(len(text), pos + 600)
            overlap = any(s <= pos <= e for s, e in seen_ranges)
            if not overlap:
                seen_ranges.append((start, end))
                snippets.append(text[start:end])
            idx = pos + 1

    if not snippets:
        return ""
    combined = " ... ".join(snippets)
    return combined[:max_chars]


def _fetch_risk_factors(doc_url: str) -> str:
    """
    下载 10-K HTML，从 Item 1 (Business) + Item 1A (Risk Factors) 提取供应链段落。
    策略：两个区段分别用关键词定位，拼接后给 LLM。
    """
    try:
        resp = requests.get(doc_url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        raw = resp.text

        # Strip HTML tags
        plain = _TAG_RE.sub(' ', raw)
        plain = re.sub(r'\s+', ' ', plain)

        # Item 1A: pick longest match (skip TOC entry)
        item1a = ""
        for m in _ITEM_1A_RE.finditer(plain):
            candidate = m.group(1).strip()
            if len(candidate) > len(item1a):
                item1a = candidate

        # Item 1 (Business): pick longest match
        item1 = ""
        for m in _ITEM_1_RE.finditer(plain):
            candidate = m.group(1).strip()
            if len(candidate) > len(item1):
                item1 = candidate

        # Extract supplier-relevant paragraphs from both sections
        snip1  = _extract_supply_snippets(item1,   max_chars=4000)
        snip1a = _extract_supply_snippets(item1a,  max_chars=4000)

        combined = ""
        if snip1:
            combined += "[Business section]\n" + snip1
        if snip1a:
            combined += "\n\n[Risk Factors section]\n" + snip1a

        if combined:
            print(f"    [supply_chain] 提取到供应链段落 {len(combined)} chars (item1={len(snip1)}, item1a={len(snip1a)})")
            return combined[:8000]

        # Fallback: first 8000 chars of Item 1A
        return item1a[:8000] or plain[:8000]
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
    "\n\nReturn ONLY valid JSON — a list of objects with keys: "
    '"supplier_name" (string), "dependency_type" '
    '("sole_source"|"single_source"|"limited_alternatives"|"qualified_supply_list"|"concentration_risk"|"other"), '
    '"evidence_quote" (≤80 chars from the text), "is_public_company" (true|false). '
    "List at most 8 entries. If no specific named dependencies found, return []."
)


def _extract_suppliers_llm(text: str, company_name: str) -> list[dict]:
    """调用 Groq LLM 从 Risk Factors 文本提取供应商列表。"""
    if not text:
        return []
    user_msg = (
        f"Company: {company_name}\n\n"
        f"Risk Factors excerpt:\n{text[:6000]}\n\n"
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


# ── 主扫描函数 ────────────────────────────────────────────────────────────────

def run_supply_chain_scan(ticker: str, company_name: str = "") -> dict:
    """
    全流程：SEC → 10-K → LLM 提取 → 打分 → 写库。
    返回 {"ok": bool, "links": [...], "error": str|None}
    """
    ticker = ticker.upper().split(".")[0]
    print(f"[supply_chain] 开始扫描 {ticker}")

    # 1. CIK
    cik = _ticker_to_cik(ticker)
    if not cik:
        return {"ok": False, "links": [], "error": f"CIK not found for {ticker}"}

    # 2. 10-K URL
    doc_url = _get_latest_10k_url(cik)
    if not doc_url:
        return {"ok": False, "links": [], "error": "No 10-K filing found"}

    # 3. Risk Factors text
    rf_text = _fetch_risk_factors(doc_url)
    if not rf_text:
        return {"ok": False, "links": [], "error": "Could not extract Risk Factors"}

    # 4. LLM extraction
    suppliers = _extract_suppliers_llm(rf_text, company_name or ticker)
    print(f"    [supply_chain] LLM 提取到 {len(suppliers)} 个供应商")

    # 5. Score + ticker lookup
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
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

        link = {
            "downstream_code":  ticker,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  dep.get("dependency_type", "other"),
            "chokepoint_score": score,
            "evidence_quote":   (dep.get("evidence_quote") or "")[:80],
            "scanned_at":       now,
            "source":           "sec_10k",
        }
        links.append(link)

    # 6. Write to DB
    if links:
        _save_links(ticker, links)

    return {"ok": True, "links": links, "error": None}


def _save_links(downstream_code: str, links: list[dict]) -> None:
    """DELETE Tier-1 + INSERT — Tier-2 rows are NOT deleted here (handled by _save_multihop)."""
    with get_conn() as c:
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
                   scanned_at, source, hop_depth, upstream_path, tier1_code)
                VALUES
                  (:downstream_code, :supplier_name, :supplier_ticker,
                   :dependency_type, :chokepoint_score, :evidence_quote,
                   :scanned_at, :source,
                   :hop_depth, :upstream_path, :tier1_code)
                """,
                {
                    **lnk,
                    "hop_depth":     lnk.get("hop_depth", 1),
                    "upstream_path": lnk.get("upstream_path"),
                    "tier1_code":    lnk.get("tier1_code"),
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
                   upstream_path, tier1_code
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

            tier2_all.append({
                "downstream_code":  ticker,
                "supplier_name":    lnk["supplier_name"],
                "supplier_ticker":  lnk.get("supplier_ticker"),
                "dependency_type":  lnk.get("dependency_type", "other"),
                "chokepoint_score": lnk.get("chokepoint_score", 40),
                "evidence_quote":   lnk.get("evidence_quote", ""),
                "scanned_at":       now,
                "source":           lnk.get("source", "cninfo_annual" if market == "cn" else "sec_10k"),
                "hop_depth":        2,
                "upstream_path":    json.dumps([ticker, sup_ticker]),
                "tier1_code":       sup_ticker,
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
                       scanned_at, source, hop_depth, upstream_path, tier1_code)
                    VALUES
                      (:downstream_code, :supplier_name, :supplier_ticker,
                       :dependency_type, :chokepoint_score, :evidence_quote,
                       :scanned_at, :source, :hop_depth, :upstream_path, :tier1_code)
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


def _get_cn_annual_report_pdf_url(code: str) -> str | None:
    """
    通过 AKShare CNINFO 接口获取最新年报的 PDF 下载 URL。
    code: 6位A股代码（如 '600519'）
    """
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            category="年报",
            start_date=start,
            end_date=end,
        )
        if df.empty:
            return None
        # 取最新一条正文年报（排除英文版/摘要/港股格式/更正）
        for _, row in df.iterrows():
            title = row.get("公告标题", "")
            if any(k in title for k in ("英文", "摘要", "更正", "港股公告", "H股")):
                continue
            link = row.get("公告链接", "")
            # Extract announcementId from the link
            m = re.search(r'announcementId=(\d+)', link)
            ann_date_m = re.search(r'announcementTime=([0-9-]+)', link)
            if m and ann_date_m:
                ann_id = m.group(1)
                ann_date = ann_date_m.group(1)
                pdf_url = f"https://static.cninfo.com.cn/finalpage/{ann_date}/{ann_id}.PDF"
                return pdf_url
    except Exception as e:
        print(f"    [supply_chain_cn] CNINFO URL lookup failed: {e}")
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
        resp = requests.get(pdf_url, headers=CNINFO_HEADERS, timeout=40)
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
    A股供应链扫描：优先 CNINFO 年报 PDF → LLM；CNINFO 不可达时降级为纯 LLM 知识。
    code: 6位A股代码（如 '600519'）
    """
    code = code.zfill(6)
    print(f"[supply_chain_cn] 开始扫描 A股 {code}")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # 1. 获取年报 PDF URL（CNINFO，可能因海外 DNS 不可达而失败）
    pdf_url = _get_cn_annual_report_pdf_url(code)
    if not pdf_url:
        print(f"    [supply_chain_cn] CNINFO 不可达，降级为 LLM 知识扫描")
        links = _cn_llm_fallback_scan(code, company_name, now)
        if links:
            _save_links(code, links)
        return {"ok": bool(links), "links": links, "error": None if links else "LLM 未返回数据"}

    print(f"    [supply_chain_cn] 年报 PDF: {pdf_url}")

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

        links.append({
            "downstream_code":  code,
            "supplier_name":    name,
            "supplier_ticker":  sup_ticker,
            "dependency_type":  "concentration_risk" if (ratio and ratio >= 30) else "other",
            "chokepoint_score": score,
            "evidence_quote":   (s.get("evidence_quote") or "")[:80],
            "scanned_at":       now,
            "source":           "cninfo_annual",
        })

    if links:
        _save_links(code, links)

    return {"ok": True, "links": links, "error": None}


def run_supply_chain_scan_auto(code: str, market: str, company_name: str = "") -> dict:
    """
    自动路由：A股走 CNINFO 年报，美股走 SEC 10-K。
    """
    if market == "cn":
        return run_cn_supply_chain_scan(code, company_name)
    else:
        # US/HK/NZ 等走原 SEC 路径（HK/NZ无EDGAR，会返回 CIK not found）
        return run_supply_chain_scan(code, company_name)
