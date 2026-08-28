#!/usr/bin/env python3
"""US-142「谁在卖自己公司的股票」—— 内部人增减持，半年窗口 + 双分母 + 惯例/机会性。

为什么换源：原 `institutional_radar.fetch_insider_changes` 走
`ak.stock_share_hold_change_sse/szse`，从 NZ 和 Fly 悉尼都 ConnectionReset →
生产 `insider_changes` 四个月只攒下 11 行。东财 datacenter 从 Fly 可达且字段全是
结构化的（CHANGE_RATIO / END_HOLD_NUM / CHANGE_REASON），比解析公告标题可靠得多。
⚠️ 东财只能在 Fly 悉尼跑，GHA 美国 runner 连不上（与 precursor scan 同一约束）。
⚠️ US-158 修订（2026-08-16）：「地理」这个说法不准确。
两地实测（scripts/probe_datasource_reach.py，GHA 美国 + 新西兰本地）结果一致：
东财 push2 两地都通、push2his（历史K线）两地都被拒 —— 是东财在拒绝这类
客户端特征，不是地理封锁。Fly 悉尼能跑通的具体是哪些 datacenter 端点尚未
逐个复测，所以下面的安排先保持不动，但别再把「地理」当成既定原因去推理。

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

# US-177：超过这个天数，就不能再当成「现在的信号」讲。
# 60 天≈一个季度，足够让一轮行情走完 —— 奥来德那 4 个月里股价翻倍又腰斩。
STALE_DAYS = int(os.environ.get("INSIDER_STALE_DAYS", "60"))

# 惯例性原因：与「看空/看多公司」无关的机械交易 → 无信息量
_ROUTINE_REASONS = ("股权激励", "行权", "解禁", "送转", "分红", "继承", "赠与",
                    # US-200：员工持股计划也属这一类。研究上二者的共同点是
                    # **不是个人看多的表达** —— 员工持股计划参与面广、
                    # 无硬性业绩考核、侧重「利益共享」；股权激励有强制考核、
                    # 按预设条件行权。两者都是**公司安排的制度**，
                    # 不是「某个人今天觉得便宜所以自掏腰包买」。
                    "员工持股", "持股计划", "激励对象", "限制性股票",
                    "回购注销", "股份支付")
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
    elif routine_reason and direction == "buy":
        # US-200：原来写的是 `routine_reason and not big` —— 只要金额够大，
        # 股权激励行权也会被当成主动增持。**那是错的，而且是机制层面的错。**
        #
        # ⚠️ **但只对买入侧成立 —— 买卖是不对称的：**
        #   买入：股权激励行权是**被动**的，解锁条件到了就行权，
        #         行不行权取决于考核和税务，不取决于他此刻怎么看公司
        #   卖出：拿到股票后**卖多少、什么时候卖，是自己的选择** ——
        #         哪怕股票来源是股权激励，「卖掉本人持股一半」仍然是主动决定
        #
        # 第一版我把这条改成了对买卖都生效，被既有测试
        # test_big_sale_is_opportunistic_even_if_reason_mechanical 当场抓到。
        #
        # 股权激励 / 员工持股 与主动增持的区别不在金额，在**性质**：
        #   股权激励：按预设条件行权，有强制业绩考核，价格往往低于市价 ——
        #             是「履行激励计划的必要程序」，行不行权更多取决于
        #             解锁条件和个人税务，不取决于他此刻怎么看公司
        #   主动增持：自掏腰包按市价买 —— 才是「我看好，我下注」
        #
        # 一次 2 亿的股权激励行权，说明的是「三年前定的考核达标了」，
        # 不是「他今天觉得便宜」。**金额再大也换不来这个含义。**
        kind = "routine"
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
        "age_recent": "，最近一笔 {n} 天前",
        "age_months": "，最近一笔已是 {n} 个月前",
        "cluster": "{n} 位内部人在 {d} 天内先后买入（{tx} 笔，合计 {r:.2f}% 股本，约 {amt}）"
                   " —— 这是内部人信号里最强的形态",
        "cluster_weak": "{n} 位内部人在 {d} 天内先后买入，但合计只有 {r:.2f}% 股本"
                        "（约 {amt}）—— 人数够了但**金额太小**，"
                        "更像员工持股或例行增持，不当强信号看",
        # US-198 更正：原文写「公告本身还要滞后几周」—— 那是**美股 Form 4**
        # 的规则（多数 21 天以上）。A股完全不同，实测最快 **1 天**就能拿到
        # （688551 / 002049 变动 08-26 → 08-27 抓到）。我当时直接套用了
        # 美股规则，从没验证过 —— 而这个错的方向危险：它会让人放弃一个
        # 其实很及时的信号。
        "horizon": "怎么用这条：内部人买入的超额收益**大半在头一个月就兑现**"
                   "（约 1/4 在头 5 天、约 1/2 在头 1 个月）。"
                   "好消息是 A股披露很快 —— 实测最快 **1 天**就能看到，"
                   "所以**及时看到的话，这条信号基本是完整的**；"
                   "隔了一两个月才看到，那就只剩「自己人当时怎么看」的参考价值了。",
        # US-198：说清「不是数据慢，是没及时看到」—— 数据 1 天就到了。
        "stale_note": "⚠️ 这些交易发生在 {n} 个月前。内部人买入的超额收益"
                      "**大半在头一个月内就走完了** —— 到现在，这条作为入场信号"
                      "基本已经失效。\n"
                      "注意：**不是数据慢**（A股实测最快 1 天就能拿到），是这条"
                      "已经过去太久。它仍能说明「自己人当时有信心」，"
                      "那是基本面的一条证据，不是现在该买的理由。",
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
        "age_recent": ", most recent {n} days ago",
        "age_months": ", most recent was {n} months ago",
        "cluster": "{n} insiders bought within {d} days ({tx} transactions, {r:.2f}% of shares outstanding, ~{amt})"
                   " — the strongest form of insider signal",
        "cluster_weak": "{n} insiders bought within {d} days, but only {r:.2f}% of shares outstanding "
                        "(~{amt}) — enough people, **too little money**. Looks like an employee "
                        "share plan or routine top-up, not a strong signal",
        "horizon": "How to read this: most of the abnormal return from insider buying lands **within the "
                   "first month** (~1/4 in the first 5 days, ~1/2 in the first month). The good news is "
                   "that A-share disclosure is fast — measured as little as **1 day** — so if you see it "
                   "promptly the signal is largely intact. Seen a month or two later, it is only evidence "
                   "of **what insiders thought at the time**.",
        "stale_note": "⚠️ These trades happened {n} months ago. Most of the abnormal return from insider "
                      "buying lands **within the first month**, so as an entry signal this has largely "
                      "expired. Note this is **not a data lag** — A-share disclosure runs as fast as one "
                      "day. It still tells you insiders were confident **at the time**: a fundamental "
                      "data point, not a reason to buy today.",
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


# US-178：cluster buy —— 多个内部人在短窗口内先后买入。
#
# 文献一致认为这是内部人信号里**最强的形态**：
#   · Lakonishok & Lee (2001)：多人同时买时，预测力显著提升
#   · Cohen, Malloy & Pomorski (2012)「Decoding Inside Information」：
#     opportunistic（打破自身惯例的）交易，超额收益约为不加区分信号的 **4 倍**
#   · OpenInsider 把 cluster_buys 列为 "the strongest open-market signal"
#   · 小盘股内部人买入，**12 个月**尺度超额收益约 7.4%
#
# 最后一条决定了措辞：**这是以月计的信号，不是今天买明天涨。**
# 用户妈妈看到 4 月的买入说「这个滞后的消息没有意义」—— 她按「日内触发」
# 的标准衡量它，而我们的页面确实把它摆在了实时信号旁边。错在呈现，不在数据。
# 实际上奥来德那一条是教科书级的 cluster buy（3 人、5 笔、一周内、约 2.5% 股本），
# 而股价此后从约 24 涨到 62.89 —— 信号是对的，只是它的尺度是月不是天。
CLUSTER_WINDOW_DAYS = int(os.environ.get("INSIDER_CLUSTER_DAYS", "30"))
CLUSTER_MIN_INSIDERS = 2

# ── US-195：光有人数不算 cluster，还要看**赌注多大** ────────────────
#
# 2026-08-29 用户妈妈实拍误报：页面标
#   「★ 8 位内部人在 1 天内先后买入（8 笔，合计 **0.02%** 股本）
#     —— 这是内部人信号里最强的形态」
#
# 对照奥来德那次**真**的 cluster：3 人、5 笔、**2.83%** 股本 —— **差 140 倍**。
#
# 生产实测过去三个月全部 15 组「cluster」的占股本比例：
#
#     002049  8 人   0.022%
#     688551  2 人   0.128%   ← 全场最高
#     600458 11 人   0.000%   ← 11 个人，占股本 0.000%
#     002601  4 人   0.007%
#
# **没有一组接近 2.83%。** 600458 那条尤其说明问题：11 个人同时买、
# 合计占股本 0.000% —— 这不可能是主动看多，是员工持股计划/股权激励行权。
#
# 文献里 cluster buy 之所以是最强形态，恰恰因为「多人**用真金白银**同时
# 下注」。0.02% 不是真金白银。US-183 只判了「人数 ≥2」和「窗口 ≤30 天」，
# **漏掉了最关键的那一维**。
# 门槛的来历（US-200，2026-08-29 查文献后修正）：
#
# 我第一版拍了「0.5% 股本 或 5000 万」——**5000 万太高了**。
# 实证研究（高管增持事件策略）：
#   · 增持金额下限 **250万–400万** 就有可用的信号价值，年化超额约 22%
#   · 金额下限越高，最优持有期越长（250万→10日、300万→30日、400万→45日）
#   · 董监高增持公告后 90 日平均超额 **+3.8%**，显著高于个人和公司股东
#
# 但也不能只看绝对金额 —— 一家 3000 亿市值的公司里 300 万等于没有。
# 所以两条并存、任一达标即可：
#   占股本 ≥0.3%   → 相对量够（小盘股走这条）
#   金额 ≥1000 万  → 绝对量够（大盘股走这条），取研究下限 400 万的
#                     2.5 倍，因为我们要的是「值得单独推一条微信」的
#                     强信号，不是「有统计价值」的边缘信号
CLUSTER_MIN_RATIO = float(os.environ.get("INSIDER_CLUSTER_MIN_RATIO", "0.3"))
CLUSTER_MIN_AMOUNT = float(os.environ.get("INSIDER_CLUSTER_MIN_AMOUNT", "1e7"))


def detect_cluster_buy(ops: list, window_days: int = None) -> dict:
    """在自主择时的**买入**里找 cluster：window 天内 ≥2 个不同的人。

    只看 buy —— 卖出的理由可能很私人（买房、缴税），多人同时卖也可能是
    解禁期到了；买入没有这种「不得不」的理由，所以 cluster buy 才是强信号。
    """
    from datetime import date as _date
    w = window_days or CLUSTER_WINDOW_DAYS
    buys = []
    for x in ops or []:
        if x.get("direction") != "buy":
            continue
        d = str(x.get("change_date") or "")[:10]
        try:
            buys.append((_date.fromisoformat(d), x))
        except (ValueError, TypeError):
            continue
    if len(buys) < CLUSTER_MIN_INSIDERS:
        return {}
    buys.sort(key=lambda t: t[0])

    best = {}
    for i, (d0, _) in enumerate(buys):
        names, ratio, n_tx, last, amount = set(), 0.0, 0, d0, 0.0
        for d1, x in buys[i:]:
            if (d1 - d0).days > w:
                break
            nm = (x.get("holder_name") or "").strip()
            if nm:
                names.add(nm)
            try:
                ratio += abs(float(x.get("ratio_total") or 0))
            except (TypeError, ValueError):
                pass
            n_tx += 1
            last = d1
            try:
                amount += abs(float(x.get("shares") or 0)) * float(x.get("avg_price") or 0)
            except (TypeError, ValueError):
                pass
        if len(names) >= CLUSTER_MIN_INSIDERS and len(names) > len(best.get("names", ())):
            best = {"names": names, "n_insiders": len(names), "n_tx": n_tx,
                    "ratio_total": round(ratio, 2), "amount": amount,
                    "start": d0.isoformat(), "end": last.isoformat(),
                    "span_days": (last - d0).days}
    if not best:
        return {}
    best.pop("names", None)

    # US-195：赌注够大才叫「最强形态」。两条任一达标即可 ——
    # 小盘股 0.5% 股本可能金额不大，大盘股 5000 万可能占比很小，
    # 单用一条会漏掉其中一类。
    big_ratio = best["ratio_total"] >= CLUSTER_MIN_RATIO
    big_amount = best.get("amount", 0) >= CLUSTER_MIN_AMOUNT
    best["is_strong"] = bool(big_ratio or big_amount)
    return best


def describe_insider_activity(moves: list, locale: str = "zh") -> dict:
    """把一只股票近半年的内部人交易讲成人话。moves = DB 行或 fetch 结果。

    只陈述观察 + 给出情境，不下「该卖」结论（US-68 语言原则）。
    """
    L = _STR.get(locale) or _STR["zh"]
    rows = list(moves or [])
    if not rows:
        # US-177：早返回也要带齐字段，否则模板读到 KeyError。
        # 「没有数据」和「有数据但很旧」都要能安全渲染。
        return {"has_data": False, "headline": L["none"], "items": [],
                "routine_skipped": 0, "caveat": "", "net_direction": None,
                "latest_date": "", "days_since": None,
                "is_stale": False, "stale_note": "",
                "cluster": {}, "cluster_note": "", "horizon_note": "", "decay": {}}

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

    # US-177：说清楚「最近一笔是多久以前」。
    #
    # 2026-08-25 用户妈妈实拍：奥来德 688378 的卡片写「近半年内部人净买入」，
    # 列出的最新一笔是 **2026-04-30** —— 已经 4 个月前，而这 4 个月里股价
    # 从 ~24 涨到 62.89 又跌回 42.22。她的原话：
    #     「这个内部人士买入是 4 月」「这个信息就太滞后了」「这个滞后的消息没有意义」
    #
    # 卡片没撒谎（确实在「近半年」窗口内），但「近半年内部人净买入」这句话
    # 读起来是**现在的状态**，而它描述的是四个月前的动作。
    # 而且列表按重要性排序、不按时间，所以用户得自己一条条看日期才发现。
    #
    # 这和「股价还没反应」是同一个病：**把过去发生过的事讲成现在的状态**。
    cluster = detect_cluster_buy(op)
    days_since = None
    latest_date = ""
    for x in op:
        d = str(x.get("change_date") or "")[:10]
        if d and d > latest_date:
            latest_date = d
    if latest_date:
        try:
            from datetime import date as _date
            days_since = (_date.today() - _date.fromisoformat(latest_date)).days
        except (ValueError, TypeError):
            days_since = None

    is_stale = days_since is not None and days_since >= STALE_DAYS

    if not op:
        head = L["none"] if not routine else L["routine_note"].format(n=routine)
    else:
        head = L["net_sell"] if net == "sell" else (L["net_buy"] if net == "buy" else L["net_sell"])
        if days_since is not None:
            if days_since >= 60:
                head += L["age_months"].format(n=max(1, round(days_since / 30)))
            else:
                head += L["age_recent"].format(n=days_since)

    # US-180：把半衰期画出来。「4 个月前」是个日期，「还剩 7% 效力」是个判断。
    decay = {}
    if days_since is not None:
        try:
            from radar_app.data.signal_layers import decay_view
            decay = decay_view(days_since, "insider")
        except Exception:
            decay = {}

    return {
        "has_data": bool(op),
        "decay": decay,
        "headline": head,
        "items": items,
        "routine_skipped": routine,
        "routine_note": L["routine_note"].format(n=routine) if routine and op else "",
        "caveat": L["caveat"] if op else "",
        "net_direction": net,
        "cluster": cluster,
        "cluster_note": (
            L["cluster" if cluster.get("is_strong") else "cluster_weak"].format(
                n=cluster["n_insiders"], d=max(1, cluster["span_days"]),
                tx=cluster["n_tx"], r=cluster["ratio_total"],
                amt=_fmt_amount(cluster.get("amount", 0) / 1.0, 1.0, locale) or "金额不详")
            if cluster else ""),
        "horizon_note": L["horizon"] if op else "",
        "latest_date": latest_date,
        "days_since": days_since,
        "is_stale": is_stale,
        "stale_note": (L["stale_note"].format(n=max(1, round(days_since / 30)))
                       if is_stale else ""),
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
