#!/usr/bin/env python3
"""US-142「谁在卖自己公司的股票」—— 内部人增减持，半年窗口 + 双分母 + 惯例/机会性。

为什么换源：原 `institutional_radar.fetch_insider_changes` 走
`ak.stock_share_hold_change_sse/szse`，从 NZ 和 Fly 悉尼都 ConnectionReset →
生产 `insider_changes` 四个月只攒下 11 行。东财 datacenter 从 Fly 可达且字段全是
结构化的（CHANGE_RATIO / END_HOLD_NUM / CHANGE_REASON），比解析公告标题可靠得多。
⚠️ 东财只能在 Fly 悉尼跑，GHA 美国 runner 连不上（与 precursor scan 同一约束）。

为什么要区分惯例 vs 机会性：内部人交易是学术上少数稳健的异常，但
Cohen-Malloy-Pomorski (2012) 证明**只有机会性交易有信息量** —— 股权激励行权、
每年固定时点的小额减持是噪音，不区分会误报一堆，反而把用户对提示的信任耗光。
"""
import os
import sys
import time
from datetime import date, datetime, timedelta

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import requests

_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REPORT = "RPT_EXECUTIVE_HOLD_DETAILS"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

WINDOW_DAYS = int(os.environ.get("INSIDER_WINDOW_DAYS", "180"))

# 惯例性原因：与「看空/看多公司」无关的机械交易 → 无信息量
_ROUTINE_REASONS = ("股权激励", "行权", "解禁", "送转", "分红", "继承", "赠与",
                    "司法", "划转", "换股", "要约")
# 占本人持股比例达到这个量级才算「动真格」（低于此且原因惯例 = 噪音）
_MEANINGFUL_OWN_PCT = 5.0
# 占总股本比例达到这个量级，无论原因都值得看
_MEANINGFUL_TOTAL_PCT = 0.1
# 绝对金额门槛（元）：**只看比例会漏掉大股东** —— 持股基数大的人卖一大笔，
# 「占本人持股」永远显得小。真实案例：002414 黄立(创始人)一笔卖 1461 万股、
# 占总股本 0.34%，但只占他本人持股 1.32% → 纯比例判定会误判成噪音。
_MEANINGFUL_AMOUNT = 1e7
# 刻意协商的交易通道：不存在「机械发生」的可能，是减持最典型的路径，永不算惯例
_DELIBERATE_VEHICLES = ("大宗交易", "协议转让", "询价转让", "集中竞价减持")
# 核心决策人：他们的动作比普通高管更有信息量
_KEY_ROLES = ("董事长", "总经理", "总裁", "实际控制人", "控股股东", "首席执行官")


def classify_insider_move(shares, ratio_total, ratio_own, reason: str = "",
                          position: str = "", avg_price=None) -> dict:
    """纯规则：一笔内部人交易 → {direction, kind, is_key_person, weight}。

    direction: sell / buy（shares 负数=卖）
    kind: routine（机械交易，无信息量）/ opportunistic（自主择时，有信息量）

    三个「动真格」判据取或（缺一个就会漏）：
      占本人持股 ≥5%（小股东的大动作）
      占总股本 ≥0.1%（对股价有实际冲击）
      绝对金额 ≥1000 万（大股东卖一大笔，但比例显得小 —— 002414 真实案例）
    """
    sh = float(shares or 0)
    direction = "sell" if sh < 0 else "buy"
    rt = abs(float(ratio_total or 0))
    ro = abs(float(ratio_own or 0))
    rsn = str(reason or "")
    pos = str(position or "")
    is_key = any(k in pos for k in _KEY_ROLES)

    try:
        amount = abs(sh) * float(avg_price or 0)
    except Exception:
        amount = 0.0

    big = (ro >= _MEANINGFUL_OWN_PCT or rt >= _MEANINGFUL_TOTAL_PCT
           or amount >= _MEANINGFUL_AMOUNT)
    deliberate = any(k in rsn for k in _DELIBERATE_VEHICLES)
    routine_reason = any(k in rsn for k in _ROUTINE_REASONS)

    if deliberate:
        kind = "opportunistic"          # 刻意协商的通道，没有「机械发生」的可能
    elif routine_reason and not big:
        kind = "routine"                # 机械原因 + 不大 = 噪音
    else:
        kind = "opportunistic" if big else "routine"

    weight = 0.0
    if kind == "opportunistic":
        weight = min(3.0, ro / 10.0 + rt * 2 + min(amount / 1e8, 1.0))
        if is_key:
            weight += 1.0
    return {
        "direction": direction, "kind": kind,
        "is_key_person": is_key, "weight": round(weight, 2),
    }


_STR = {
    "zh": {
        "sell_one": "{who}卖了自己公司的股票",
        "buy_one": "{who}买了自己公司的股票",
        "denom": "卖出{total:.2f}%的总股本，相当于他持股的{own:.0f}%",
        "denom_buy": "买入{total:.2f}%的总股本",
        "amount": "，约 {amt}",
        "amount_only": "约 {amt}",
        "denom_own_only": "卖掉了他持股的{own:.0f}%",
        "colon": "：",
        "key": "（核心决策人）",
        "routine_note": "另有 {n} 笔属股权激励/解禁一类的机械交易，与看多看空无关，未计入",
        "none": "近半年没有高管或大股东买卖自己公司股票的记录",
        "net_sell": "近半年内部人净卖出",
        "net_buy": "近半年内部人净买入",
        "caveat": "高管卖股票的理由可能很私人（买房、缴税），一笔不说明问题；连续、大额、多人同时卖才值得当信号。",
    },
    "en": {
        "sell_one": "{who} sold shares in their own company",
        "buy_one": "{who} bought shares in their own company",
        "denom": "sold {total:.2f}% of all shares outstanding — about {own:.0f}% of what they personally held",
        "denom_buy": "bought {total:.2f}% of all shares outstanding",
        "amount": ", roughly {amt}",
        "amount_only": "roughly {amt}",
        "denom_own_only": "about {own:.0f}% of what they personally held",
        "colon": ": ",
        "key": " (key decision-maker)",
        "routine_note": "{n} more transactions were mechanical (equity incentives, lock-up expiry) and carry no view on the company — excluded",
        "none": "No insider buying or selling on record in the last six months",
        "net_sell": "Insiders were net sellers over the last six months",
        "net_buy": "Insiders were net buyers over the last six months",
        "caveat": "An executive may sell for entirely personal reasons (a house, a tax bill). One sale means little — repeated, large, or several people selling at once is what matters.",
    },
}


def _fmt_amount(shares, avg_price, locale="zh") -> str:
    """成交金额人话化。**百分比会掩盖绝对量级** —— 大股东卖 1461 万股只占他持股 1%，
    读起来像小事，加上「约 2 亿」才有感觉。"""
    try:
        amt = abs(float(shares or 0)) * float(avg_price or 0)
    except Exception:
        return ""
    if amt < 1e6:
        return ""
    if locale == "en":
        # A 股按人民币计价，别标成美元
        # 英文不用「亿」这个单位，一律折成 million（2 亿 = RMB 197 million）
        return f"RMB {amt/1e6:.0f} million"
    if amt >= 1e8:
        return f"{amt/1e8:.1f}亿元"
    return f"{amt/1e4:.0f}万元"


def describe_insider_activity(moves: list, locale: str = "zh") -> dict:
    """把一只股票近半年的内部人交易讲成人话。moves = DB 行或 fetch 结果。

    只陈述观察 + 给出情境，不下「该卖」结论（US-68 语言原则）。
    """
    L = _STR.get(locale) or _STR["zh"]
    rows = list(moves or [])
    if not rows:
        return {"has_data": False, "headline": L["none"], "items": [],
                "routine_skipped": 0, "caveat": "", "net_direction": None}

    op, routine = [], 0
    for m in rows:
        c = classify_insider_move(m.get("shares"), m.get("ratio_total"),
                                 m.get("ratio_own"), m.get("reason"),
                                 m.get("role"), m.get("avg_price"))
        if c["kind"] == "routine":
            routine += 1
            continue
        op.append({**m, **c})

    op.sort(key=lambda x: -x["weight"])
    sells = sum(1 for x in op if x["direction"] == "sell")
    buys = len(op) - sells
    net = None
    if op:
        net = "sell" if sells > buys else ("buy" if buys > sells else None)

    items = []
    for x in op[:5]:
        who = (x.get("holder_name") or "") + (L["key"] if x["is_key_person"] else "")
        tmpl = L["sell_one"] if x["direction"] == "sell" else L["buy_one"]
        line = tmpl.format(who=who.strip())
        rt = abs(float(x.get("ratio_total") or 0))
        ro = abs(float(x.get("ratio_own") or 0))
        amt = _fmt_amount(x.get("shares"), x.get("avg_price"), locale)
        # 占比不足 0.01% 时别写「0.00%」—— 那是噪音，反而削弱可信度；让金额说话
        rt_shown = rt >= 0.005
        if x["direction"] == "sell" and ro and rt_shown:
            line += L["colon"] + L["denom"].format(total=rt, own=ro)
        elif x["direction"] == "sell" and ro:
            line += L["colon"] + L["denom_own_only"].format(own=ro)
        elif rt_shown:
            line += L["colon"] + L["denom_buy"].format(total=rt)
        elif amt:
            line += L["colon"] + L["amount_only"].format(amt=amt)
            amt = ""
        if amt:
            line += L["amount"].format(amt=amt)
        items.append({"text": line, "date": x.get("change_date", ""),
                      "direction": x["direction"], "weight": x["weight"]})

    if not op:
        head = L["none"] if not routine else L["routine_note"].format(n=routine)
    else:
        head = L["net_sell"] if net == "sell" else (L["net_buy"] if net == "buy" else L["net_sell"])

    return {
        "has_data": bool(op),
        "headline": head,
        "items": items,
        "routine_skipped": routine,
        "routine_note": L["routine_note"].format(n=routine) if routine and op else "",
        "caveat": L["caveat"] if op else "",
        "net_direction": net,
    }


def _fetch_code(code: str, days: int, retries: int = 3):
    """拉单只股票近 N 天的内部人交易。东财 datacenter，Fly 悉尼可达。"""
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "reportName": _REPORT, "columns": "ALL", "pageSize": 100, "pageNumber": 1,
        "sortColumns": "CHANGE_DATE", "sortTypes": -1,
        "filter": f'(SECURITY_CODE="{code}")(CHANGE_DATE>=\'{since}\')',
    }
    last = None
    for i in range(retries):
        try:
            r = requests.get(_URL, params=params, timeout=25, headers=_HEADERS)
            return ((r.json() or {}).get("result") or {}).get("data") or []
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    print(f"    ⚠️ {code} 内部人数据拉取失败: {str(last)[:60]}")
    return []


def _own_pct(shares, end_hold):
    """占本人持股 % —— 卖出用「卖前持股」作分母才有意义（卖前 = 卖后 + 卖掉的）。"""
    try:
        sh = abs(float(shares or 0))
        end = float(end_hold or 0)
        base = end + sh if float(shares or 0) < 0 else end
        return round(sh / base * 100, 2) if base > 0 else None
    except Exception:
        return None


def run_insider_refresh(codes, days: int = None) -> dict:
    """抓自选股近半年内部人交易 → 存 insider_changes。返回统计。"""
    import db

    days = days or WINDOW_DAYS
    codes = [str(c).split(".")[0].zfill(6) for c in codes]
    codes = [c for c in codes if c.isdigit()]
    saved = 0
    with_moves = 0

    for code in codes:
        rows = _fetch_code(code, days)
        if not rows:
            continue
        with_moves += 1
        for d in rows:
            shares = d.get("CHANGE_SHARES")
            ratio_own = _own_pct(shares, d.get("END_HOLD_NUM"))
            cls = classify_insider_move(shares, d.get("CHANGE_RATIO"), ratio_own,
                                        d.get("CHANGE_REASON"), d.get("POSITION_NAME"),
                                        d.get("AVERAGE_PRICE"))
            try:
                db.upsert_insider_change(
                    code=code,
                    holder_name=str(d.get("PERSON_NAME") or ""),
                    role=str(d.get("POSITION_NAME") or d.get("PERSON_DSE_RELATION") or ""),
                    change_type=cls["direction"],
                    shares=abs(float(shares or 0)),
                    avg_price=float(d.get("AVERAGE_PRICE") or 0) or None,
                    change_date=str(d.get("CHANGE_DATE") or "")[:10],
                    ratio_total=abs(float(d.get("CHANGE_RATIO") or 0)) or None,
                    ratio_own=ratio_own,
                    reason=str(d.get("CHANGE_REASON") or ""),
                    kind=cls["kind"],
                )
                saved += 1
            except Exception as e:
                print(f"    ⚠️ {code} 存库失败: {str(e)[:60]}")
        time.sleep(0.4)   # 温柔串行，别把东财惹了（US-122 教训）

    return {"codes": len(codes), "with_moves": with_moves, "saved": saved}


if __name__ == "__main__":
    import db

    db.init_db()
    if "--smoke" in sys.argv:
        # 冒烟：拿几只真股票验证源可达 + 字段解析 + 人话输出
        test = ["600519", "000333", "002414"]
        print(f"🔍 内部人交易冒烟测试（{WINDOW_DAYS} 天窗口）: {test}")
        for c in test:
            rows = _fetch_code(c, WINDOW_DAYS)
            print(f"  {c}: {len(rows)} 条原始记录")
            parsed = [{
                "holder_name": d.get("PERSON_NAME"), "role": d.get("POSITION_NAME"),
                "shares": d.get("CHANGE_SHARES"), "ratio_total": d.get("CHANGE_RATIO"),
                "ratio_own": _own_pct(d.get("CHANGE_SHARES"), d.get("END_HOLD_NUM")),
                "reason": d.get("CHANGE_REASON"), "change_date": str(d.get("CHANGE_DATE"))[:10],
                "avg_price": d.get("AVERAGE_PRICE"),
            } for d in rows]
            for loc in ("zh", "en"):
                r = describe_insider_activity(parsed, locale=loc)
                print(f"    [{loc}] {r['headline']}（机械交易跳过 {r['routine_skipped']} 笔）")
                for it in r["items"][:2]:
                    print(f"        · {it['date']} {it['text']}")
        raise SystemExit(0)

    codes = [c for c, _ in db.get_all_cn_watchlist_stocks()]
    print(f"👤 内部人交易刷新：{len(codes)} 只 A股，{WINDOW_DAYS} 天窗口")
    print("  ", run_insider_refresh(codes))
