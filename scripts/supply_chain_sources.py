"""
US-106 · 跨境供应链三源融合

数据源优先级：
  ① A股年报客户字段反查 (CNINFO)   — 置信度 95，强制披露的官方数据
  ② ImportYeti 美国海关数据        — 置信度 90，真实货运提单
  ③ 财报电话会议 (yfinance)        — 置信度 70，管理层口头披露

主入口：
  scan_a_share_customers(code, name)  → 扫单只A股，写 supply_chain_customer_index
  batch_scan_all_cn_watchlist()       → 批量扫妈妈所有A股
  get_us_suppliers_for_ticker(us_ticker) → 查某美股的A股供应商（含来源和置信度）
  scan_importyeti(us_ticker)          → 从ImportYeti找中国供应商
  scan_earnings_call(us_ticker)       → 从财报电话找供应商
"""

import json
import re
import time
from datetime import datetime, timedelta

import requests

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths
bootstrap_paths()

from scripts.buffett_groq import _call_groq
from radar_app.data.core import get_conn, CN_TZ

# ══════════════════════════════════════════════════════════════════════════════
# 共用工具
# ══════════════════════════════════════════════════════════════════════════════

CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://www.cninfo.com.cn/",
}

_US_TICKER_CACHE: dict[str, str | None] = {}


def _match_us_ticker(customer_name: str) -> str | None:
    """
    把年报里的客户名（可能是中文或英文）匹配到美股 ticker。
    先做本地常见名称映射，再用 yfinance 搜索。
    """
    if not customer_name:
        return None
    key = customer_name.strip().lower()
    if key in _US_TICKER_CACHE:
        return _US_TICKER_CACHE[key]

    # 常见中英文名称静态映射（只做高置信度的大公司）
    _KNOWN: dict[str, str] = {
        "apple": "AAPL", "苹果": "AAPL", "apple inc": "AAPL",
        "microsoft": "MSFT", "微软": "MSFT",
        "tesla": "TSLA", "特斯拉": "TSLA",
        "nvidia": "NVDA", "英伟达": "NVDA",
        "intel": "INTC", "英特尔": "INTC",
        "qualcomm": "QCOM", "高通": "QCOM",
        "broadcom": "AVGO", "博通": "AVGO",
        "amazon": "AMZN", "亚马逊": "AMZN",
        "google": "GOOGL", "alphabet": "GOOGL", "谷歌": "GOOGL",
        "meta": "META", "facebook": "META",
        "boeing": "BA", "波音": "BA",
        "lockheed martin": "LMT", "洛克希德": "LMT",
        "ge": "GE", "通用电气": "GE",
        "ford": "F", "福特": "F",
        "gm": "GM", "通用汽车": "GM",
        "lumentum": "LITE",
        "ii-vi": "IIVI", "coherent": "COHR",
        "ams": "AMS",
        "huawei": None,  # 未上市
        "xiaomi": "1810.HK",
        "samsung": None,  # 韩股，暂不处理
    }
    for k, v in _KNOWN.items():
        if k in key:
            _US_TICKER_CACHE[key] = v
            return v

    # yfinance 搜索
    try:
        import yfinance as yf
        results = yf.Search(customer_name, max_results=3)
        for q in (results.quotes or []):
            ticker = q.get("symbol", "")
            qtype = (q.get("quoteType") or "").upper()
            exchange = (q.get("exchange") or "").upper()
            if not ticker or qtype in {"ETF", "MUTUALFUND", "INDEX"}:
                continue
            # 只取主要美股交易所
            if exchange in {"NMS", "NYQ", "NGM", "NCM", "PCX", "ASE"}:
                _US_TICKER_CACHE[key] = ticker
                return ticker
    except Exception:
        pass

    _US_TICKER_CACHE[key] = None
    return None


def _save_customer_rows(rows: list[dict]) -> int:
    """写入 supply_chain_customer_index，跳过重复，返回新增行数。"""
    inserted = 0
    with get_conn() as c:
        for r in rows:
            try:
                c.execute(
                    """
                    INSERT OR REPLACE INTO supply_chain_customer_index
                      (a_share_code, a_share_name, customer_name, us_ticker,
                       revenue_pct, source, report_year, scanned_at, confidence)
                    VALUES
                      (:a_share_code, :a_share_name, :customer_name, :us_ticker,
                       :revenue_pct, :source, :report_year, :scanned_at, :confidence)
                    """,
                    r,
                )
                inserted += 1
            except Exception as e:
                print(f"    [sc_sources] insert error: {e}")
    return inserted


def get_us_suppliers_for_ticker(us_ticker: str) -> list[dict]:
    """
    查某美股的所有A股供应商（跨三个来源），按置信度降序。
    返回字段：a_share_code, a_share_name, customer_name, revenue_pct,
              source, report_year, confidence, scanned_at
    """
    us_ticker = us_ticker.upper().split(".")[0]
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT a_share_code, a_share_name, customer_name,
                   us_ticker, revenue_pct, source, report_year,
                   confidence, scanned_at
            FROM   supply_chain_customer_index
            WHERE  us_ticker = :ticker
            ORDER BY confidence DESC, revenue_pct DESC NULLS LAST
            """,
            {"ticker": us_ticker},
        ).fetchall()
    return [dict(r) for r in rows]


def is_customer_scan_fresh(a_share_code: str, max_days: int = 60) -> bool:
    """检查某A股的客户扫描是否在 max_days 内。"""
    with get_conn() as c:
        row = c.execute(
            "SELECT scanned_at FROM supply_chain_customer_index "
            "WHERE a_share_code = :code ORDER BY scanned_at DESC LIMIT 1",
            {"code": a_share_code},
        ).fetchone()
    if not row:
        return False
    try:
        t = datetime.fromisoformat(row["scanned_at"])
        return (datetime.now() - t.replace(tzinfo=None)).days < max_days
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 数据源 ①：A股年报客户字段反查
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_CN_CUSTOMER = (
    "你是供应链分析师，分析A股上市公司年报中的客户信息。\n"
    "给定年报文本（可能包含「前五大客户」「主要客户」「客户集中度」等章节），"
    "提取每个客户的名称和收入占比。\n\n"
    "规则：\n"
    "1. customer_name 必须是真实公司名，可以是中文或英文。\n"
    "2. revenue_pct 是该客户占公司营收的百分比（数字，无需%符号），无则填null。\n"
    "3. is_foreign 表示是否为境外公司（包括美国、欧洲、日本等）。\n"
    "4. 最多返回8条，优先返回境外大客户。\n\n"
    "返回合法JSON列表，每项含：customer_name, revenue_pct, is_foreign, "
    "evidence_quote(≤60字原文引用)。不要返回JSON之外的任何文字。"
)

_CN_CUSTOMER_KW = [
    "前五大客户", "前五名客户", "主要客户", "客户集中度",
    "前十大客户", "前三大客户", "客户名称", "最终客户",
    "境外收入", "出口客户",
]


def _fetch_cn_customer_text(pdf_url: str) -> str:
    """从年报PDF提取客户相关页面，策略同供应商提取但关键词不同。"""
    try:
        import pdfplumber, io
        resp = requests.get(pdf_url, headers=CNINFO_HEADERS, timeout=40)
        resp.raise_for_status()

        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            all_pages = [(i, page.extract_text() or "") for i, page in enumerate(pdf.pages)]

        # 找含客户关键词的页面
        customer_idx: set[int] = set()
        for i, text in all_pages:
            if any(kw in text for kw in _CN_CUSTOMER_KW):
                customer_idx.add(i)
                customer_idx.add(i + 1)

        ordered = [all_pages[i][1] for i in sorted(customer_idx) if i < len(all_pages)]
        combined = "\n\n".join(ordered[:6])
        if not combined.strip():
            return ""
        print(f"    [sc_sources①] 客户页面 {len(ordered)} 页，{len(combined)} chars")
        return combined[:5000]
    except ImportError:
        print("    [sc_sources①] pdfplumber 未安装")
    except Exception as e:
        print(f"    [sc_sources①] PDF 提取失败: {e}")
    return ""


def scan_a_share_customers(code: str, name: str = "") -> list[dict]:
    """
    扫描单只A股年报，提取客户信息写入 supply_chain_customer_index。
    返回新写入的行列表。
    """
    code = code.zfill(6)
    print(f"[sc_sources①] 扫描A股客户: {code} {name}")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # 获取年报 PDF URL（复用 supply_chain_mapper 的函数）
    try:
        from scripts.supply_chain_mapper import _get_cn_annual_report_pdf_url
        pdf_url = _get_cn_annual_report_pdf_url(code)
    except Exception as e:
        print(f"    [sc_sources①] PDF URL 获取失败: {e}")
        pdf_url = None

    customers_raw = []

    if pdf_url:
        text = _fetch_cn_customer_text(pdf_url)
        if text:
            user_msg = (
                f"公司：{name or code}（A股代码：{code}）\n\n"
                f"年报客户相关内容：\n{text}\n\n"
                "请提取客户信息，返回JSON列表。"
            )
            raw = _call_groq(_SYSTEM_CN_CUSTOMER, user_msg, max_tokens=600)
            m = re.search(r'\[.*\]', raw or "", re.DOTALL)
            if m:
                try:
                    customers_raw = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

    if not customers_raw:
        # LLM 知识兜底：直接问 Groq 这家公司有哪些已知的境外大客户
        print(f"    [sc_sources①] PDF 无结果，用 LLM 知识兜底")
        fallback_prompt = (
            "你是供应链分析师。根据你的训练数据，列出以下A股公司已知的主要境外客户。\n"
            "只列你有高置信度的客户，不要猜测。\n"
            "返回合法JSON列表，每项含：customer_name, revenue_pct(null if unknown), "
            "is_foreign(true), evidence_quote(注明'基于公开信息')。"
        )
        user_msg = f"公司：{name or code}（A股代码：{code}）\n请列出已知的主要境外大客户。"
        raw = _call_groq(fallback_prompt, user_msg, max_tokens=400)
        m = re.search(r'\[.*\]', raw or "", re.DOTALL)
        if m:
            try:
                customers_raw = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    print(f"    [sc_sources①] LLM 提取到 {len(customers_raw)} 个客户")

    # 提取年份
    report_year = datetime.now().year - 1

    rows = []
    for c_item in customers_raw:
        cname = (c_item.get("customer_name") or "").strip()
        if not cname or len(cname) < 2:
            continue
        # 只处理境外客户（目标是找美股）
        if not c_item.get("is_foreign"):
            continue
        revenue_pct = c_item.get("revenue_pct")
        try:
            revenue_pct = float(revenue_pct) if revenue_pct is not None else None
        except (TypeError, ValueError):
            revenue_pct = None

        us_ticker = _match_us_ticker(cname)
        time.sleep(0.2)

        source = "cninfo_annual" if pdf_url else "llm_knowledge"
        confidence = 95 if pdf_url else 60

        rows.append({
            "a_share_code":  code,
            "a_share_name":  name,
            "customer_name": cname,
            "us_ticker":     us_ticker,
            "revenue_pct":   revenue_pct,
            "source":        source,
            "report_year":   report_year,
            "scanned_at":    now,
            "confidence":    confidence,
        })

    inserted = _save_customer_rows(rows)
    print(f"    [sc_sources①] 写入 {inserted} 条客户记录")
    return rows


def batch_scan_all_cn_watchlist() -> dict:
    """
    批量扫描所有用户自选A股的年报客户字段。
    适合作为每周 pipeline 任务运行一次。
    """
    from radar_app.data.stocks import get_all_cn_watchlist_stocks
    stocks = get_all_cn_watchlist_stocks()
    print(f"[sc_sources①] 批量扫描 {len(stocks)} 只A股客户字段")

    total_new = 0
    for code, name in stocks:
        if is_customer_scan_fresh(code, max_days=60):
            print(f"    跳过 {code} {name}（60天内已扫）")
            continue
        try:
            rows = scan_a_share_customers(code, name)
            total_new += len(rows)
        except Exception as e:
            print(f"    [sc_sources①] {code} 扫描失败: {e}")
        time.sleep(1)  # 避免CNINFO频率限制

    print(f"[sc_sources①] 批量完成，共写入 {total_new} 条新客户记录")
    return {"ok": True, "total_new": total_new, "scanned": len(stocks)}


# ══════════════════════════════════════════════════════════════════════════════
# 数据源 ②：ImportYeti 美国海关数据
# ══════════════════════════════════════════════════════════════════════════════

_IMPORTYETI_SEARCH = "https://www.importyeti.com/api/company/search"
_IMPORTYETI_SHIPMENTS = "https://www.importyeti.com/api/company/{slug}/suppliers"
_IY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.importyeti.com/",
}


def _iy_get_company_slug(company_name: str) -> str | None:
    """用 ImportYeti 搜索接口找公司 slug。"""
    try:
        resp = requests.get(
            _IMPORTYETI_SEARCH,
            params={"query": company_name},
            headers=_IY_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results") or data.get("companies") or []
        if results:
            return results[0].get("slug") or results[0].get("id")
    except Exception as e:
        print(f"    [sc_sources②] ImportYeti search failed: {e}")
    return None


def _iy_get_suppliers(slug: str) -> list[dict]:
    """拉取 ImportYeti 某公司的供应商列表。"""
    try:
        url = _IMPORTYETI_SHIPMENTS.format(slug=slug)
        resp = requests.get(url, headers=_IY_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("suppliers") or data.get("results") or []
    except Exception as e:
        print(f"    [sc_sources②] ImportYeti suppliers failed: {e}")
    return []


def scan_importyeti(us_ticker: str, company_name: str = "") -> list[dict]:
    """
    从 ImportYeti 获取某美股公司的中国供应商，
    匹配 A 股代码，写入 supply_chain_customer_index（source='importyeti'）。
    """
    us_ticker = us_ticker.upper().split(".")[0]
    search_name = company_name or us_ticker
    print(f"[sc_sources②] ImportYeti 扫描: {us_ticker} ({search_name})")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    slug = _iy_get_company_slug(search_name)
    if not slug:
        print(f"    [sc_sources②] 未找到公司: {search_name}")
        return []

    suppliers = _iy_get_suppliers(slug)
    print(f"    [sc_sources②] ImportYeti 返回 {len(suppliers)} 个供应商")

    from scripts.supply_chain_mapper import _lookup_cn_ticker

    rows = []
    for s in suppliers[:20]:  # 最多取前20个
        supplier_name = (
            s.get("name") or s.get("supplier_name") or s.get("company_name") or ""
        ).strip()
        if not supplier_name:
            continue

        # 只处理中国供应商
        country = (s.get("country") or s.get("origin_country") or "").upper()
        if country and country not in ("CN", "CHINA", "CHN", ""):
            continue

        shipment_count = s.get("shipment_count") or s.get("total_shipments") or 0

        # 尝试匹配 A 股代码
        a_code = _lookup_cn_ticker(supplier_name)

        rows.append({
            "a_share_code":  a_code or f"_IY_{supplier_name[:20]}",
            "a_share_name":  supplier_name,
            "customer_name": company_name or us_ticker,
            "us_ticker":     us_ticker,
            "revenue_pct":   None,
            "source":        "importyeti",
            "report_year":   datetime.now().year,
            "scanned_at":    now,
            "confidence":    90 if a_code else 70,
        })

    # 只保存成功匹配到A股代码的（没有代码的留着供展示但不加入自选股流程）
    valid_rows = [r for r in rows if not r["a_share_code"].startswith("_IY_")]
    if valid_rows:
        _save_customer_rows(valid_rows)
    print(f"    [sc_sources②] 匹配到A股代码: {len(valid_rows)}/{len(rows)}")

    # 返回全部（含未匹配的，前端展示用）
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# 数据源 ③：财报电话会议
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_EARNINGS_CALL = (
    "You are a supply-chain analyst reviewing an earnings call transcript. "
    "Extract any specific supplier or manufacturing partner names mentioned, "
    "especially Chinese companies or suppliers based in China/Asia. "
    "Return ONLY valid JSON — a list of objects with keys: "
    '"supplier_name" (string, real company name only — no generic terms), '
    '"context" (≤80 chars of what was said), '
    '"is_chinese_company" (true|false). '
    "Skip vague references like 'our suppliers' or 'contract manufacturers'. "
    "Return [] if no specific suppliers named. Max 10 entries."
)


def scan_earnings_call(us_ticker: str, company_name: str = "") -> list[dict]:
    """
    从 yfinance 获取最新财报电话会议记录，提取供应商信息，
    写入 supply_chain_customer_index（source='earnings_call'）。
    """
    us_ticker = us_ticker.upper().split(".")[0]
    print(f"[sc_sources③] 财报电话会议扫描: {us_ticker}")
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    transcript_text = ""
    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(us_ticker)
        # yfinance 在某些版本有 earnings_history 或 transcript
        # 主要尝试 news 里的 earnings call 相关内容
        news = ticker_obj.news or []
        ec_articles = [
            n for n in news
            if any(kw in (n.get("title", "") + n.get("summary", "")).lower()
                   for kw in ["earnings call", "conference call", "transcript", "q&a"])
        ]
        if ec_articles:
            # 拼接摘要作为近似替代
            transcript_text = " ".join(
                (a.get("summary") or a.get("title") or "")
                for a in ec_articles[:5]
            )
    except Exception as e:
        print(f"    [sc_sources③] yfinance 获取失败: {e}")

    if len(transcript_text) < 100:
        print(f"    [sc_sources③] 无足够的电话会议内容")
        return []

    raw = _call_groq(_SYSTEM_EARNINGS_CALL,
                     f"Company: {company_name or us_ticker}\n\nTranscript:\n{transcript_text[:5000]}",
                     max_tokens=600)
    m = re.search(r'\[.*\]', raw or "", re.DOTALL)
    if not m:
        return []

    try:
        suppliers_raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []

    print(f"    [sc_sources③] LLM 提取到 {len(suppliers_raw)} 个供应商")

    from scripts.supply_chain_mapper import _lookup_cn_ticker

    rows = []
    for s in suppliers_raw:
        sname = (s.get("supplier_name") or "").strip()
        if not sname or len(sname) < 3:
            continue
        if not s.get("is_chinese_company"):
            continue

        a_code = _lookup_cn_ticker(sname)
        rows.append({
            "a_share_code":  a_code or f"_EC_{sname[:20]}",
            "a_share_name":  sname,
            "customer_name": company_name or us_ticker,
            "us_ticker":     us_ticker,
            "revenue_pct":   None,
            "source":        "earnings_call",
            "report_year":   datetime.now().year,
            "scanned_at":    now,
            "confidence":    70 if a_code else 50,
        })

    valid_rows = [r for r in rows if not r["a_share_code"].startswith("_EC_")]
    if valid_rows:
        _save_customer_rows(valid_rows)
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# 综合入口：扫描一只美股，跑全部三个数据源
# ══════════════════════════════════════════════════════════════════════════════

def scan_all_sources(us_ticker: str, company_name: str = "") -> dict:
    """
    对一只美股同时触发三个数据源扫描。
    返回 {"ok": True, "results": {source: [rows]}, "total": n}
    """
    us_ticker = us_ticker.upper().split(".")[0]
    results: dict[str, list] = {}

    # ① 批量扫描所有A股年报（看谁把这只美股列为客户）— 异步触发，不阻塞
    # 注意：batch_scan 很慢（扫全部A股），这里只对已有结果做查询
    # 实时触发改为：只扫妈妈持仓里还没扫过的A股
    from radar_app.data.stocks import get_all_cn_watchlist_stocks
    cn_stocks = get_all_cn_watchlist_stocks()
    source1_rows = []
    for code, name in cn_stocks:
        if not is_customer_scan_fresh(code, max_days=60):
            try:
                rows = scan_a_share_customers(code, name)
                source1_rows.extend(rows)
                time.sleep(0.5)
            except Exception as e:
                print(f"    [scan_all] ① {code} 失败: {e}")
    results["cninfo_annual"] = source1_rows

    # ② ImportYeti
    try:
        results["importyeti"] = scan_importyeti(us_ticker, company_name)
    except Exception as e:
        print(f"    [scan_all] ② ImportYeti 失败: {e}")
        results["importyeti"] = []

    # ③ 财报电话
    try:
        results["earnings_call"] = scan_earnings_call(us_ticker, company_name)
    except Exception as e:
        print(f"    [scan_all] ③ 财报电话失败: {e}")
        results["earnings_call"] = []

    total = sum(len(v) for v in results.values())
    print(f"[scan_all_sources] {us_ticker} 完成，三源合计 {total} 条")
    return {"ok": True, "results": results, "total": total}
