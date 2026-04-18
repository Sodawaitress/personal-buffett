"""
US-46 · 公司分类器
添加股票时自动运行，判断 company_type / st_status / market_tier。
"""
import re
import sys
import os
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()
import db

# ── ST 状态检测 ────────────────────────────────────────

def _detect_st_status(name: str) -> str | None:
    """从股票名称判断 ST 状态。"""
    name_upper = name.upper()
    if "*ST" in name_upper or "＊ST" in name_upper:
        return "*ST"
    if "SST" in name_upper:
        return "SST"
    if re.search(r'\bST\b', name_upper):
        return "ST"
    return None


# ── 市场层级检测 ───────────────────────────────────────

def _detect_market_tier(code: str, market: str) -> str:
    """根据代码判断上市板块。"""
    pure = code.split(".")[0]

    if market == "cn":
        if pure.startswith("688") or pure.startswith("689"):
            return "star"    # 科创板
        if pure.startswith("300") or pure.startswith("301"):
            return "sme"     # 创业板
        return "main"        # 主板

    if market == "hk":
        # 港股 GEM：代码以 8 或 4 开头（如 8611, 4位数）
        if pure.startswith("8") or pure.startswith("4"):
            return "gem"
        return "main"

    if market == "nz":
        # NXT 市场股票通常有特定后缀，目前统一归 main
        return "main"

    return "main"


# ── ETF/基金代码前缀（A股）────────────────────────────

_CN_ETF_PREFIXES = ("159", "510", "511", "512", "513", "515", "516", "517",
                    "518", "519", "588", "560", "561", "562", "563", "164",
                    "165", "166", "167", "168")

_FUND_NAME_KW = ("ETF", "LOF", "FOF", "基金", "混合", "货币市场", "债券型",
                 "股票型", "指数型", "增强型", "QDII", "量化")

def _is_etf(code: str, name: str) -> bool:
    """检测是否为 ETF 或基金产品（含场外基金）。"""
    name_up = name.upper()
    if any(k.upper() in name_up for k in _FUND_NAME_KW):
        return True
    pure = code.split(".")[0]
    if pure.startswith(_CN_ETF_PREFIXES):
        return True
    return False


# ── 行业关键词匹配 ─────────────────────────────────────

_FINANCIAL_KW  = {"银行", "保险", "券商", "信托", "金融", "证券", "资管",
                   "bank", "insurance", "financial"}
_CYCLICAL_KW   = {"钢铁", "煤炭", "化工", "地产", "建材", "有色", "铝", "铜",
                   "矿", "石油", "能源", "steel", "coal", "chemical", "property"}
_UTILITY_KW    = {"电力", "水务", "燃气", "热力", "公用", "供电", "自来水",
                   "utility", "power", "water", "gas"}
_GROWTH_KW     = {"科技", "软件", "互联网", "半导体", "芯片", "生物", "医药",
                   "人工智能", "AI", "云", "tech", "software", "internet",
                   "semiconductor", "biotech", "pharma"}


def _match_kw(text: str, kw_set: set) -> bool:
    text_lower = text.lower()
    return any(k.lower() in text_lower for k in kw_set)


# ── 主分类函数 ─────────────────────────────────────────

def classify_stock(code: str) -> dict:
    """
    读取 DB 中该股票的基本信息和财务数据，返回分类结果 dict。
    同时写入 stock_meta 表。
    """
    stock        = db.get_stock(code) or {}
    fundamentals = db.get_fundamentals(code) or {}

    name   = stock.get("name", "") or stock.get("name_cn", "")
    market = stock.get("market", "us")
    sector = stock.get("sector", "") or ""

    # 1. ST 状态
    st_status   = _detect_st_status(name)
    market_tier = _detect_market_tier(code, market)

    # 2. 公司类型
    import json
    annual = []
    try:
        annual = json.loads(fundamentals.get("annual_json") or "[]")
    except Exception:
        pass

    # 连续2年以上亏损 → pre_profit（ROE 可能是字符串，如 "12.5%"，需转 float）
    def _to_float(v):
        if v is None:
            return None
        try:
            return float(str(v).replace("%", "").strip())
        except (ValueError, TypeError):
            return None

    neg_roe_years = sum(
        1 for y in annual[:3]
        if _to_float(y.get("roe")) is not None and _to_float(y["roe"]) < 0
    )

    # 读取最新一期财务指标，用于 speculative 判断
    latest_roe    = _to_float(annual[0].get("roe"))    if annual else None
    latest_margin = _to_float(annual[0].get("net_margin")) if annual else None
    latest_debt   = _to_float(annual[0].get("debt_ratio"))  if annual else None
    try:
        pb_current = float(fundamentals.get("pb_current") or 0) or None
    except Exception:
        pb_current = None

    # GEM 市场 + 财务恶化 → speculative（优先于 growth_tech）
    # 判据：GEM 板块 且 以下任一条件成立：
    #   - ROE < 0（当期亏损）
    #   - 净利率 < 0（亏损公司）
    #   - 负债率 > 85%（偿债风险）
    #   - PB > 30 且 ROE < 5%（泡沫估值 + 盈利极弱）
    is_speculative = market_tier == "gem" and (
        (latest_roe    is not None and latest_roe    < 0)   or
        (latest_margin is not None and latest_margin < 0)   or
        (latest_debt   is not None and latest_debt   > 85)  or
        (pb_current is not None and pb_current > 30
         and (latest_roe is None or latest_roe < 5))
    )

    if _is_etf(code, name):
        company_type = "etf"
    elif st_status in ("ST", "*ST", "SST"):
        company_type = "distressed"
    elif is_speculative:
        company_type = "speculative"
    elif _match_kw(sector, _FINANCIAL_KW):
        company_type = "financial"
    elif _match_kw(sector, _UTILITY_KW):
        company_type = "utility"
    elif _match_kw(sector, _CYCLICAL_KW):
        company_type = "cyclical"
    elif market_tier in ("star", "gem") or _match_kw(sector, _GROWTH_KW):
        company_type = "growth_tech"
    elif neg_roe_years >= 2:
        # 区分「成熟公司暂时亏损」vs「真正的未盈利初创」：
        # 如果历史上有3年以上盈利记录（ROE > 5%），说明是周期性困境，不是初创
        profitable_years = sum(
            1 for y in annual
            if _to_float(y.get("roe")) is not None and _to_float(y["roe"]) > 5
        )
        company_type = "mature_value" if profitable_years >= 3 else "pre_profit"
    else:
        company_type = "mature_value"

    result = {
        "company_type": company_type,
        "market_tier":  market_tier,
        "st_status":    st_status,
        "industry":     sector or None,
    }

    db.upsert_stock_meta(code, **result)
    return result


def classify_all_watchlist():
    """对所有自选股跑一次分类（用于 launchd 季度任务或手动触发）。"""
    with db.get_conn() as c:
        rows = c.execute("SELECT DISTINCT stock_code FROM user_watchlist").fetchall()
    codes = [r["stock_code"] for r in rows]
    results = {}
    for code in codes:
        try:
            results[code] = classify_stock(code)
            print(f"  {code}: {results[code]['company_type']} / "
                  f"tier={results[code]['market_tier']} / "
                  f"st={results[code]['st_status']}")
        except Exception as e:
            print(f"  {code}: ERROR {e}")
    return results


if __name__ == "__main__":
    db.init_db()
    print("分类所有自选股…")
    classify_all_watchlist()
