"""
institutional_radar.py — 机构行为追踪

识别三类机构操盘模式：
  出货  — 股价涨 + 主力净流出（机构卖给追涨散户）
  吸筹  — 股价跌 + 超大单净流入（机构趁跌建仓）
  北向背离 — 外资大幅流出（聪明钱在跑）

附加：解禁预警（未来14天有大额解禁）
"""

from datetime import datetime, timedelta

import akshare as ak

from scripts.config import CN_TZ


# ── 工具 ─────────────────────────────────────────────────────────────

def _cn_codes():
    try:
        import db
        return [code for code, _ in db.get_all_cn_watchlist_stocks()]
    except Exception:
        return []


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ── 1. 龙虎榜：机构净买卖 ──────────────────────────────────────────

def fetch_lhb_signals(days: int = 7) -> dict:
    """
    返回 {code: {"inst_net_buy": 亿, "buy_count": N, "sell_count": N, "dates": [...]}}
    inst_net_buy > 0 = 机构净买入，< 0 = 净卖出
    """
    codes = set(_cn_codes())
    now = datetime.now(CN_TZ)
    start = (now - timedelta(days=days)).strftime("%Y%m%d")
    end   = now.strftime("%Y%m%d")

    result = {}
    try:
        df = ak.stock_lhb_jgmmtj_em(start_date=start, end_date=end)
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            if code not in codes:
                continue
            net   = _safe_float(row.get("机构买入净额", 0)) / 1e8
            buy_n = int(_safe_float(row.get("买方机构数", 0)))
            sel_n = int(_safe_float(row.get("卖方机构数", 0)))
            date  = str(row.get("上榜日期", ""))
            if code not in result:
                result[code] = {"inst_net_buy": 0.0, "buy_count": 0, "sell_count": 0, "dates": []}
            result[code]["inst_net_buy"] += net
            result[code]["buy_count"]   += buy_n
            result[code]["sell_count"]  += sel_n
            if date and date not in result[code]["dates"]:
                result[code]["dates"].append(date)
    except Exception as e:
        print(f"  ⚠️ 龙虎榜拉取失败: {e}")

    return result


# ── 2. 北向资金 ───────────────────────────────────────────────────

def fetch_northbound_signal() -> dict:
    """
    返回 {"sh_net": 亿, "sz_net": 亿, "total_net": 亿, "signal": str}
    """
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        north = df[df["资金方向"] == "北向"]
        sh = north[north["板块"] == "沪股通"]["资金净流入"].sum()
        sz = north[north["板块"] == "深股通"]["资金净流入"].sum()
        total = _safe_float(sh) + _safe_float(sz)
        if total >= 50:
            signal = "大幅流入"
        elif total >= 10:
            signal = "温和流入"
        elif total >= -10:
            signal = "基本持平"
        elif total >= -50:
            signal = "温和流出"
        else:
            signal = "大幅流出"
        return {"sh_net": _safe_float(sh), "sz_net": _safe_float(sz),
                "total_net": total, "signal": signal}
    except Exception as e:
        print(f"  ⚠️ 北向资金拉取失败: {e}")
        return {}


# ── 3. 解禁预警 ───────────────────────────────────────────────────

def fetch_restricted_releases(days_ahead: int = 14) -> list:
    """
    返回未来 days_ahead 天内自选股的解禁事件列表
    [{"code": str, "name": str, "date": str, "ratio": float, "amount_bn": float}]
    """
    codes = set(_cn_codes())
    now   = datetime.now(CN_TZ)
    start = now.strftime("%Y%m%d")
    end   = (now + timedelta(days=days_ahead)).strftime("%Y%m%d")

    releases = []
    try:
        df = ak.stock_restricted_release_detail_em(start_date=start, end_date=end)
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).zfill(6)
            if code not in codes:
                continue
            ratio = _safe_float(row.get("占解禁前流通市值比例", 0)) * 100
            if ratio < 1.0:
                continue
            releases.append({
                "code":      code,
                "name":      str(row.get("股票简称", code)),
                "date":      str(row.get("解禁时间", "")),
                "ratio":     ratio,
                "amount_bn": _safe_float(row.get("实际解禁市值", 0)) / 1e8,
                "type":      str(row.get("限售股类型", "")),
            })
    except Exception as e:
        print(f"  ⚠️ 解禁日历拉取失败: {e}")

    return releases


# ── 4. 模式识别 ───────────────────────────────────────────────────

def detect_patterns(quotes: dict, fund_flow: dict, lhb: dict) -> dict:
    """
    返回 {code: [pattern_dict, ...]}

    模式：
      出货  — 涨 + 主力净流出（机构借涨出货）
      吸筹  — 跌 + 超大单净流入（机构趁跌建仓）
      龙虎出货 — LHB 机构净卖出 > 1亿
      龙虎吸筹 — LHB 机构净买入 > 1亿
    """
    patterns = {}
    for code in _cn_codes():
        q  = quotes.get(code, {})
        ff = fund_flow.get(code, {})
        lb = lhb.get(code, {})

        change   = _safe_float(q.get("change", 0))
        main_net = _safe_float(ff.get("main_net", 0))
        super_net = _safe_float(ff.get("super_net", 0))

        found = []

        # 出货：涨价 + 主力净流出
        if change >= 2.0 and main_net <= -0.5:
            found.append({
                "type":  "出货",
                "label": "📤 疑似出货",
                "desc":  f"股价涨{change:.1f}% 但主力净流出{abs(main_net):.2f}亿——机构可能借涨向散户出货",
            })

        # 吸筹：跌价 + 超大单净流入
        if change <= -2.0 and super_net >= 0.5:
            found.append({
                "type":  "吸筹",
                "label": "📥 疑似吸筹",
                "desc":  f"股价跌{abs(change):.1f}% 但超大单净流入{super_net:.2f}亿——机构可能趁跌建仓",
            })

        # 龙虎榜：机构净卖出
        if lb.get("inst_net_buy", 0) <= -1.0:
            found.append({
                "type":  "龙虎出货",
                "label": "🐯 龙虎榜·机构卖出",
                "desc":  (f"近7日龙虎榜机构净卖出{abs(lb['inst_net_buy']):.2f}亿"
                          f"（卖方{lb['sell_count']}家 > 买方{lb['buy_count']}家）"),
            })

        # 龙虎榜：机构净买入
        if lb.get("inst_net_buy", 0) >= 1.0:
            found.append({
                "type":  "龙虎吸筹",
                "label": "🐯 龙虎榜·机构买入",
                "desc":  (f"近7日龙虎榜机构净买入{lb['inst_net_buy']:.2f}亿"
                          f"（买方{lb['buy_count']}家 > 卖方{lb['sell_count']}家）"),
            })

        if found:
            patterns[code] = found

    return patterns


# ── 5. 格式化报告片段 ────────────────────────────────────────────

def format_institutional_section(patterns: dict, northbound: dict,
                                  restricted: list, quotes: dict) -> str:
    lines = ["## 🏦 机构雷达"]

    # 北向资金
    if northbound:
        total = northbound.get("total_net", 0)
        signal = northbound.get("signal", "")
        sign = "+" if total >= 0 else ""
        direction = "📈" if total >= 0 else "📉"
        lines.append(f"\n**北向资金**：{direction} {signal}，今日净流入 **{sign}{total:.1f}亿**")
        if total <= -50:
            lines.append("> ⚠️ 外资大幅撤离，注意个股估值支撑是否仍在")

    # 个股机构模式
    if patterns:
        lines.append("\n**个股机构行为**\n")
        for code, plist in patterns.items():
            name = quotes.get(code, {}).get("name", code)
            for p in plist:
                lines.append(f"- **{name}（{code}）** {p['label']}：{p['desc']}")
    else:
        lines.append("\n**个股机构行为**：今日无明显异常模式")

    # 解禁预警
    if restricted:
        lines.append("\n**⏰ 解禁预警（14日内）**\n")
        for r in restricted:
            lines.append(
                f"- **{r['name']}（{r['code']}）** {r['date']} 解禁"
                f" ·{r['type']}· 规模{r['amount_bn']:.1f}亿"
                f"（占流通盘{r['ratio']:.1f}%）"
            )

    return "\n".join(lines)


# ── 6. 主入口（供 pipeline 调用）────────────────────────────────

def run_institutional_radar(data: dict) -> str:
    """
    传入 pipeline data dict，返回机构雷达报告片段（Markdown）
    """
    print("  🏦 机构雷达：拉取龙虎榜...")
    lhb = fetch_lhb_signals(days=7)

    print("  🏦 机构雷达：拉取北向资金...")
    northbound = fetch_northbound_signal()

    print("  🏦 机构雷达：拉取解禁日历...")
    restricted = fetch_restricted_releases(days_ahead=14)

    quotes    = data.get("quotes", {})
    fund_flow = data.get("fund_flow", {})

    print("  🏦 机构雷达：识别行为模式...")
    patterns = detect_patterns(quotes, fund_flow, lhb)

    return format_institutional_section(patterns, northbound, restricted, quotes)
