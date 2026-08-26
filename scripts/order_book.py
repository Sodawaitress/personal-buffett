"""在手订单 —— 不发中标公告的公司，订单藏在「合同负债」里（US-186）。

## 从哪来的

用户妈妈问「能不能看订单量」。US-184 查明：**中标公告只覆盖靠投标做生意的
行业**（电缆、电气设备、建筑工程、水务），而她持有的消费/医药/科技/锂电
结构上不发这种公告 —— 自选 118 只命中 0。

那这些公司的「订单」在哪？**在财报的「合同负债」科目里。**

    客户下单预付   → 现金进来，**合同负债增加**
    交付确认收入   → 合同负债**转成营收**

所以合同负债是「已经收了钱、但还没交货」的部分 —— 就是**在手订单**。

实测依据：2022 年合同负债增长的公司里，**637 家在 2023 Q1 营收增长，
占 72.63%**（新浪财经统计）。研究界也确认「预收账款+合同负债」同比增速
与利润增速正相关，对 A股整体和制造业有前瞻意义。

## 关键：光看增长不够，要和营收比

合同负债涨 50% 听起来很好，但如果营收也涨 50%，那只是生意整体在长大，
不含额外信息。真正有信息量的是**速度差**：

    订单积累速度 = 合同负债同比 − 营收同比

    差值大幅为正 → 订单积累快过交付，**未来营收还没体现**  ← 领先
    差值为负     → 在消化存量订单，未来营收可能减速

还要看**量级**：合同负债 ÷ 年营收，相当于锁定了多少个月的收入。
只有量级够大，速度差才有意义 —— 一家合同负债只占营收 1% 的公司，
它涨 100% 也不说明什么。

## 只和自己比，不跨行业比

白酒的预收款是渠道打款、工程的是订单预付、软件的是订阅预收 ——
不同行业的天然水位差好几倍。所以这里**一律只和该公司自己的历史比**，
不做横向排名。

## 按五层链，这属于「公司本身」那一层

它是**真实的经营变化**，不是市场情绪。价值不在于领先几天，在于它是真的。
代价是慢：季报频率，且披露滞后 1–2 个月。
"""

# 合同负债占年营收多少，才值得看。低于这个数，涨跌都是噪音。
_MIN_SCALE_PCT = 3.0

# 速度差多大才算「订单在积累」（百分点）
_GAP_STRONG = 20.0
_GAP_MILD = 8.0

# 不适用的行业：合同负债在这些行业是另一回事，或者天然没有
NOT_APPLICABLE = ("银行", "保险", "证券", "信托")


# A股年报里 revenue 存的是**带单位的字符串**（'4237.02亿'），美股存纯数字（亿）。
# 同一个字段两种格式 —— 又是「同一个名字两种含义」，只是这次在数据层。
_CN_UNITS = {"万亿": 1e4, "亿": 1.0, "万": 1e-4}


def _num(v):
    """转数。带中文单位的字符串一律折算成**亿**（与美股年报同口径）。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else None
    t = str(v).strip().replace(",", "")
    for unit, mult in _CN_UNITS.items():          # 「万亿」要排在「亿」「万」前面
        if t.endswith(unit):
            try:
                return float(t[:-len(unit)]) * mult
            except ValueError:
                return None
    try:
        f = float(t)
        return f if f == f else None
    except ValueError:
        return None


def order_book_signal(contract_liab, contract_liab_yoy, revenue_yoy,
                      annual_revenue, industry: str = "", locale: str = "zh") -> dict:
    """在手订单信号。

    contract_liab      最新一期合同负债（元）
    contract_liab_yoy  合同负债同比（%）
    revenue_yoy        营收同比（%）
    annual_revenue     上一个完整财年营收（元）

    返回 {} 表示算不出来或不适用 —— **不猜**。
    """
    if any(k in str(industry) for k in NOT_APPLICABLE):
        return {}
    cl = _num(contract_liab)
    cl_yoy = _num(contract_liab_yoy)
    rev_yoy = _num(revenue_yoy)
    rev = _num(annual_revenue)
    if cl is None or cl_yoy is None or rev is None or rev <= 0:
        return {}

    scale_pct = round(cl / rev * 100, 1)
    months = round(cl / (rev / 12), 1)
    if scale_pct < _MIN_SCALE_PCT:
        # 量级太小，涨跌都是噪音 —— 说清楚为什么不给结论
        return {"scale_pct": scale_pct, "months": months, "tier": "too_small",
                "text": (f"在手订单只相当于年营收的 {scale_pct}%，"
                         f"量级太小，它的增减说明不了什么")}

    gap = None if rev_yoy is None else round(cl_yoy - rev_yoy, 1)

    if gap is None:
        tier = "unknown_gap"
        text = (f"在手订单相当于 {months} 个月的营收，同比{_pm(cl_yoy)}"
                f"（缺营收同比，看不出是不是快过交付）")
    elif gap >= _GAP_STRONG:
        tier = "building"
        text = (f"在手订单相当于 {months} 个月的营收，同比{_pm(cl_yoy)}，"
                f"**比营收快 {gap:.0f} 个百分点** —— 订单积累快过交付，"
                f"这部分收入还没体现在报表上")
    elif gap >= _GAP_MILD:
        tier = "mild_building"
        text = (f"在手订单相当于 {months} 个月的营收，同比{_pm(cl_yoy)}，"
                f"略快于营收（差 {gap:.0f} 个百分点）")
    elif gap <= -_GAP_STRONG:
        tier = "draining"
        text = (f"在手订单相当于 {months} 个月的营收，同比{_pm(cl_yoy)}，"
                f"**比营收慢 {abs(gap):.0f} 个百分点** —— 在消化存量订单，"
                f"新单没跟上，未来营收可能减速")
    else:
        tier = "steady"
        text = (f"在手订单相当于 {months} 个月的营收，同比{_pm(cl_yoy)}，"
                f"和营收增速差不多 —— 订单与交付基本同步")

    if locale == "en":
        text = _en(months, cl_yoy, gap, tier)

    return {"scale_pct": scale_pct, "months": months, "cl_yoy": cl_yoy,
            "rev_yoy": rev_yoy, "gap": gap, "tier": tier, "text": text}


def revenue_yoy_from_annual(annual: list):
    """从年报算营收同比（%）。年报里 revenue 的单位是「亿」，且**有时是字符串**。

    注意别拿 profit_growth 当营收增速 —— 利润和营收是两回事，
    净利率一变就对不上（US-172 那笔一次性收益就是活例子）。
    """
    vals = []
    for y in annual or []:
        v = _num(y.get("revenue"))
        if v and v > 0:
            vals.append(v)
        if len(vals) >= 2:
            break
    if len(vals) < 2 or vals[1] <= 0:
        return None
    return round((vals[0] - vals[1]) / vals[1] * 100, 1)


def annual_revenue_yuan(annual: list):
    """最近一个完整财年营收（元）。年报单位是「亿」。"""
    for y in annual or []:
        v = _num(y.get("revenue"))
        if v and v > 0:
            return v * 1e8
    return None


def _pm(v):
    """同比的人话。|v| < 1% 时说「基本持平」——「下降 0%」是句病句
    （宁德时代实测 -0.43% 被四舍五入成 0，读起来像没变又像在跌）。"""
    if abs(v) < 1:
        return "基本持平"
    return f"增长 {v:.0f}%" if v > 0 else f"下降 {abs(v):.0f}%"


def _en(months, cl_yoy, gap, tier):
    # |v| < 1% 时说 flat —— "down 0%" 是句病句（宁德时代实测 -0.43%
    # 被四舍五入成 0，中英文都栽在同一处）
    move = ("roughly flat" if abs(cl_yoy) < 1
            else f"{'up' if cl_yoy > 0 else 'down'} {abs(cl_yoy):.0f}%")
    base = f"Order book covers about {months} months of revenue, {move} YoY"
    if tier == "building":
        return base + f" — {gap:.0f} points faster than revenue: orders are piling up ahead of delivery"
    if tier == "draining":
        return base + f" — {abs(gap):.0f} points slower than revenue: working through the backlog, new orders lagging"
    if tier == "mild_building":
        return base + f" — modestly ahead of revenue ({gap:.0f} points)"
    if tier == "unknown_gap":
        return base + " (no revenue growth to compare against)"
    return base + " — roughly in step with revenue"


# ── 抓取（US-186）────────────────────────────────────────
#
# 逐股接口约 37 秒/只，209 只要 2 小时 —— 但**这是季报数据，
# 一个季度才变一次**，不需要天天抓。所以照 US-158 行业映射那套
# 「渐进收敛」：每轮只抓一批最久没刷过的，跨天铺满，之后按季刷新。
#
# 排在最前跑（US-174/184 的教训：贵的活会把后面的饿死）。

import json
import os
import time

BATCH = int(os.environ.get("ORDER_BOOK_BATCH", "20"))
REFRESH_DAYS = int(os.environ.get("ORDER_BOOK_REFRESH_DAYS", "80"))   # 约一个季度


def _em_symbol(code: str) -> str:
    c = str(code).zfill(6)
    return ("SH" if c[0] in "56" else "BJ" if c[0] in "48" else "SZ") + c


def fetch_one(code: str) -> dict:
    """抓一只的合同负债 + 同比。返回 {} 表示抓不到 —— **不猜**。"""
    import akshare as ak
    df = ak.stock_balance_sheet_by_report_em(symbol=_em_symbol(code))
    if df is None or df.empty:
        return {}
    row = df.iloc[0]
    def _g(k):
        try:
            v = float(row.get(k))
            return v if v == v else None
        except (TypeError, ValueError):
            return None
    cl = _g("CONTRACT_LIAB")
    adv = _g("ADVANCE_RECEIVABLES")
    # 新收入准则后大部分公司用「合同负债」，少数仍用「预收账款」。
    # 两者是同一件事的两种记法，取其一 —— 相加会重复计。
    total = cl if cl else adv
    if not total:
        return {}
    return {
        "report_date": str(row.get("REPORT_DATE") or "")[:10],
        "contract_liab": total,
        "contract_liab_yoy": _g("CONTRACT_LIAB_YOY") if cl else _g("ADVANCE_RECEIVABLES_YOY"),
        "field": "contract_liab" if cl else "advance_receivables",
    }


def refresh(codes=None, batch: int = None, sleep_s: float = 1.0) -> dict:
    """渐进收敛：每轮只抓一批最久没刷过的，存进 stock_fundamentals.signals_json。"""
    import db
    from radar_app.data.core import get_conn

    n = batch or BATCH
    if codes is None:
        codes = [c for c, _ in db.get_all_cn_watchlist_stocks()]

    # 挑最久没刷的
    stale = []
    for code in codes:
        try:
            sig = (db.get_fundamentals(code) or {}).get("signals") or {}
        except Exception:
            sig = {}
        ob = sig.get("order_book") or {}
        stale.append((ob.get("fetched_at") or "", code))
    stale.sort()
    todo = [c for _, c in stale[:n]]

    done = failed = 0
    for code in todo:
        try:
            r = fetch_one(code)
            if not r:
                failed += 1
                continue
            r["fetched_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with get_conn() as c:
                row = c.execute(
                    "SELECT signals_json FROM stock_fundamentals WHERE code=:c",
                    {"c": code}).fetchone()
                try:
                    sig = json.loads((row["signals_json"] if row else "") or "{}")
                except Exception:
                    sig = {}
                sig["order_book"] = r
                c.execute(
                    "UPDATE stock_fundamentals SET signals_json=:s WHERE code=:c",
                    {"s": json.dumps(sig, ensure_ascii=False), "c": code})
            done += 1
        except Exception:
            failed += 1
        time.sleep(sleep_s)
    return {"attempted": len(todo), "done": done, "failed": failed,
            "remaining": max(0, len(codes) - done)}
