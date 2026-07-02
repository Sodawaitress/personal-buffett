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
                 "股票型", "指数型", "增强型", "QDII", "量化",
                 # 海外基金常见命名
                 "Fund", "Trust", "Hedged", "Index", "Total World",
                 "Total Market", "SmartShares", "Vanguard", "iShares",
                 "Diversified", "Fixed Interest", "NZBond", "NZCash")

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
# 金融细分（US-116：CAMELS只适用银行，券商/保险要各自尺子）
_BANK_KW       = {"银行", "bank"}
_SECURITIES_KW = {"券商", "证券", "投行", "securities", "broker"}
_INSURANCE_KW  = {"保险", "险", "insurance"}
# 结构不同的类型（US-116）：生物药看现金跑道/管线，房地产看NAV/负债三道红线
_BIOTECH_KW    = {"生物", "创新药", "生物医药", "biotech", "生物制品", "基因"}
_PROPERTY_KW   = {"房地产", "地产", "置业", "real estate", "property"}
_CYCLICAL_KW   = {"钢铁", "煤炭", "化工", "地产", "建材", "有色", "铝", "铜",
                   "矿", "石油", "能源", "steel", "coal", "chemical", "property"}
_UTILITY_KW    = {"电力", "水务", "燃气", "热力", "公用", "供电", "自来水",
                   "utility", "power", "water", "gas"}
_GROWTH_KW     = {"科技", "软件", "互联网", "半导体", "芯片", "生物", "医药",
                   "人工智能", "AI", "云", "tech", "software", "internet",
                   "semiconductor", "biotech", "pharma"}

# 供应链瓶颈关键词（非A股市场，sector 匹配任一关键词 → supply_chain 候选）
_SUPPLY_CHAIN_KW = {
    "semiconductor", "photonics", "laser", "optical", "memory", "hbm",
    "cpo", "transceiver", "wafer", "substrate", "epi", "indium",
    "gallium", "germanium", "defense optics", "thermal imaging",
    "gpu cloud", "ai infrastructure",
}


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

    # US-116 验证层：crowd/manual 定过的分类，auto 不覆盖（尊重人工/众包采信结果）
    _existing = db.get_stock_meta(code) or {}
    if _existing.get("manual_override") or _existing.get("type_source") in ("crowd", "manual"):
        return {
            "company_type": _existing.get("company_type"),
            "market_tier":  _existing.get("market_tier"),
            "st_status":    _existing.get("st_status"),
            "industry":     _existing.get("industry"),
            "_protected":   True,
        }

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

    # ── 财务签名（US-117：行为优先于行业关键词）──────────────
    # Lynch 按行为分类：快成长=利润真在增长、困境反转=曾盈利现转亏、周期=随经济起落
    _roe_hist = [_to_float(y.get("roe")) for y in annual]
    _roe_hist = [r for r in _roe_hist if r is not None]
    positive_roe_years = sum(1 for r in _roe_hist if r > 0)
    profitable_years   = sum(1 for r in _roe_hist if r > 5)
    never_profitable   = positive_roe_years == 0
    was_profitable     = positive_roe_years >= 2
    currently_losing   = latest_roe is not None and latest_roe < 0
    # 营收近几年复合增速（行为信号：是不是真的在长）
    rev_cagr_3y = None
    _revs = []
    for y in annual:
        v = y.get("revenue")
        if v is not None:
            try:
                s = str(v).strip()
                mult = 1e4 if s.endswith("亿") else 1.0
                _revs.append(float(s.rstrip("亿万")) * mult)
            except (ValueError, TypeError):
                _revs.append(None)
        else:
            _revs.append(None)
    _revs = [r for r in _revs if r is not None]
    if len(_revs) >= 2 and _revs[-1] > 0 and _revs[0] > 0:
        rev_cagr_3y = ((_revs[0] / _revs[-1]) ** (1 / (len(_revs) - 1)) - 1) * 100

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

    # supply_chain：非A股在 US Serenity 论文库、A股在 CN Serenity 论文库、或 sector 命中关键词
    _is_supply_chain = False
    try:
        from scripts.serenity_theses import SERENITY_CODES, CN_SERENITY_CODES
        pure_code = code.upper().split(".")[0]
        if market == "cn":
            if pure_code in CN_SERENITY_CODES:
                _is_supply_chain = True
        else:
            if pure_code in SERENITY_CODES or _match_kw(sector, _SUPPLY_CHAIN_KW):
                _is_supply_chain = True
    except Exception:
        pass

    if _is_etf(code, name):
        company_type = "etf"
    elif st_status in ("ST", "*ST", "SST"):
        company_type = "distressed"
    elif is_speculative:
        company_type = "speculative"
    elif _is_supply_chain:
        company_type = "supply_chain"
    elif _match_kw(sector, _FINANCIAL_KW) or _match_kw(name, _FINANCIAL_KW):
        # 金融细分：银行/券商/保险 各自尺子（CAMELS只适用银行）
        _nm_sec = f"{name} {sector}"
        if _match_kw(_nm_sec, _BANK_KW):
            company_type = "bank"
        elif _match_kw(_nm_sec, _SECURITIES_KW):
            company_type = "securities"
        elif _match_kw(_nm_sec, _INSURANCE_KW):
            company_type = "insurance"
        else:
            company_type = "financial"
    elif _match_kw(sector, _UTILITY_KW):
        company_type = "utility"
    elif _match_kw(sector, _PROPERTY_KW) or _match_kw(name, _PROPERTY_KW):
        # 房地产：看 NAV/预售/负债(三道红线)，不是通用周期（先于 cyclical，因"地产"也在周期词里）
        company_type = "property"
    elif _match_kw(sector, _CYCLICAL_KW):
        # 周期行业：随经济起落，亏是行业低谷（看周期位置，不是公司出问题）
        company_type = "cyclical"
    elif (_match_kw(sector, _BIOTECH_KW) or _match_kw(name, _BIOTECH_KW)) and (never_profitable or currently_losing):
        # 临床期生物药：看现金跑道/管线，Rule of 40 不适用（盈利的成熟药企不走这，落成长/价值）
        company_type = "biotech"
    elif never_profitable and currently_losing:
        # 从没真正盈利过 + 当前亏损 → 未盈利初创
        company_type = "pre_profit"
    elif was_profitable and currently_losing:
        # 曾经盈利 + 当前转亏 → 困境反转（看恢复趋势，不是周期）
        company_type = "turnaround"
    elif rev_cagr_3y is not None and rev_cagr_3y >= 18 and not currently_losing:
        # 营收真在高速增长 + 当前盈利 → 真·快成长
        company_type = "growth_tech"
    elif market_tier in ("star", "gem") or _match_kw(sector, _GROWTH_KW):
        # 成长板块/行业仅作 fallback 提示：盈利才算成长，亏损不再无脑 growth
        if currently_losing:
            company_type = "turnaround" if was_profitable else "pre_profit"
        else:
            company_type = "growth_tech"
    elif neg_roe_years >= 2:
        # 历史有3年以上盈利记录 → 周期性困境（成熟价值），否则未盈利初创
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
