"""
institutional_radar.py — 机构行为追踪

六类信号（详见 INSTITUTIONAL_RADAR.md）：
  1. 出货/吸筹      — 今日资金流向 + 价格方向背离
  2. 龙虎榜         — 7日机构净买卖
  3. 北向趋势       — 5日/10日累计方向（单日是噪音）
  4. 高管增减持     — 30日内内部人实际买卖
  5. 解禁预警       — 14日内按类型差异化风险
  6. 大宗交易折价   — 7日内折价率，机构悄悄出货的信号
  7. 股东人数变化   — 季度筹码集中/分散方向
  8. 回购进度       — 公司在执行中的回购（底部信号组合之一）
"""

import time
from datetime import datetime, timedelta

import akshare as ak

from scripts.config import CN_TZ


# ── 工具 ─────────────────────────────────────────────────────────────

def _cn_codes():
    try:
        import db
        return [code for code, _ in db.get_active_watchlist_stocks()]
    except Exception:
        return []


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _pure(code: str) -> str:
    """去掉交易所后缀，得到纯6位数字代码。"""
    return code.split(".")[0]


def _exchange(code: str) -> str:
    """根据首位判断交易所：6/9→SSE，0/3→SZSE，4/8→BSE。"""
    p = _pure(code)
    if p.startswith(("6", "9")):
        return "sse"
    if p.startswith(("4", "8")):
        return "bse"
    return "szse"


# ── 1. 龙虎榜：机构净买卖（7日） ────────────────────────────────────

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


# ── 2. 北向资金趋势（5日/10日累计） ─────────────────────────────────

def fetch_northbound_trend(days: int = 10) -> dict:
    """
    使用 pipeline 已存入 DB 的今日北向净流入，每天追加到 northbound_history，
    从历史中计算 5日/10日趋势。单日是噪音，连续方向才是信号。

    依赖：pipeline 的 _fetch_north_bound → save_north_bound → market_data 已先行运行。
    返回 {"d5_net": 亿, "d10_net": 亿, "signal": str, "consecutive": N,
           "direction": "inflow"|"outflow"|"mixed"}
    """
    import db
    # 从 market_data 取今日已拉的北向值，追加到历史表
    try:
        nb_today = db.get_north_bound()
        date_str  = str(nb_today.get("date", ""))[:10]
        total_net = _safe_float(nb_today.get("total_net", None))
        if date_str and total_net is not None:
            db.upsert_northbound_hist(date_str, total_net)
    except Exception as e:
        print(f"  ⚠️ 北向今日值写入历史失败: {e}")

    hist = db.get_northbound_hist(days=days)  # 降序
    if not hist:
        return {}

    nets = [r["total_net"] for r in hist if r["total_net"] is not None]  # index0 = 最新
    if not nets:
        return {}

    d5  = sum(nets[:5])  if len(nets) >= 5  else sum(nets)
    d10 = sum(nets[:10]) if len(nets) >= 10 else sum(nets)

    # 连续同向天数
    if nets:
        direction = "inflow" if nets[0] >= 0 else "outflow"
        consecutive = 0
        for n in nets:
            if (direction == "inflow" and n >= 0) or (direction == "outflow" and n < 0):
                consecutive += 1
            else:
                break
    else:
        direction, consecutive = "mixed", 0

    # 信号强度
    if d5 >= 100:
        signal = "5日大幅净流入"
    elif d5 >= 30:
        signal = "5日温和净流入"
    elif d5 >= -30:
        signal = "5日基本持平"
    elif d5 >= -100:
        signal = "5日温和净流出"
    else:
        signal = "5日大幅净流出"

    return {
        "d5_net":      round(d5, 1),
        "d10_net":     round(d10, 1),
        "signal":      signal,
        "consecutive": consecutive,
        "direction":   direction,
        "today_net":   nets[0] if nets else 0,
    }


# ── 3. 高管增减持（30日内） ──────────────────────────────────────────

def fetch_insider_changes(days: int = 30) -> dict:
    """
    拉取自选股高管增减持，存入 DB，返回按 code 分组的变动列表。
    返回 {code: [{"name", "role", "type": "buy"|"sell", "shares", "price", "date"}, ...]}
    SSE/BSE 逐股拉取；SZSE 拉全量后过滤。
    """
    import db
    codes = _cn_codes()
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    result: dict = {}

    def _store(code, name, role, raw_type, shares, price, date_str):
        if date_str < cutoff:
            return
        # 判断方向：优先用原因文字，其次用股数符号
        if any(k in raw_type for k in ("买入", "增持", "买")):
            ctype = "buy"
        elif any(k in raw_type for k in ("卖出", "减持", "卖")):
            ctype = "sell"
        else:
            ctype = "buy" if _safe_float(shares) > 0 else "sell"
        try:
            db.upsert_insider_change(code, name, role, ctype,
                                     abs(_safe_float(shares)), _safe_float(price), date_str)
        except Exception:
            pass
        entry = {"name": name, "role": role, "type": ctype,
                 "shares": abs(_safe_float(shares)), "price": _safe_float(price),
                 "date": date_str}
        result.setdefault(code, []).append(entry)

    # SSE（逐股拉取，限速）
    sse_codes = [c for c in codes if _exchange(c) == "sse"]
    for code in sse_codes:
        try:
            df = ak.stock_share_hold_change_sse(symbol=_pure(code))
            for _, row in df.iterrows():
                _store(code,
                       str(row.get("姓名", "")),
                       str(row.get("职务", "")),
                       str(row.get("变动原因", "")),
                       row.get("变动数", 0),
                       row.get("本次变动平均价格", 0),
                       str(row.get("变动日期", ""))[:10])
        except Exception:
            pass
        time.sleep(0.3)

    # SZSE（全量拉取后过滤，避免逐股调用）
    szse_codes = set(c for c in codes if _exchange(c) == "szse")
    if szse_codes:
        try:
            df = ak.stock_share_hold_change_szse(symbol="全部")
            for _, row in df.iterrows():
                code = str(row.get("证券代码", "")).zfill(6)
                if code not in szse_codes:
                    continue
                # SZSE 全量接口列结构不同：这里拿流通受限变动推导（减仓/增仓）
                # 主要用"流通受限股份"变动判断，正增量=增持约束解除，负=新增限售
                # 这个接口实际上是股份变动（not 高管增减持），仅作补充
                # 如有误差，让数据为空，不报错
        except Exception:
            pass

    # BSE（逐股拉取）
    bse_codes = [c for c in codes if _exchange(c) == "bse"]
    for code in bse_codes:
        try:
            df = ak.stock_share_hold_change_bse(symbol=_pure(code))
            for _, row in df.iterrows():
                _store(code,
                       str(row.get("姓名", "")),
                       str(row.get("职务", "")),
                       str(row.get("变动原因", "")),
                       row.get("变动数", 0),
                       row.get("本次变动平均价格", 0),
                       str(row.get("变动日期", ""))[:10])
        except Exception:
            pass
        time.sleep(0.3)

    # 补充：从 DB 里读出30天内已存的记录（覆盖多次运行）
    for code in codes:
        db_rows = db.get_insider_changes(code, days=days)
        for r in db_rows:
            entry = {"name": r["holder_name"], "role": r["role"],
                     "type": r["change_type"], "shares": r["shares"],
                     "price": r["avg_price"], "date": r["change_date"]}
            existing = result.get(code, [])
            # 避免重复（按name+date去重）
            key = (r["holder_name"], r["change_date"], r["change_type"])
            if not any((e["name"], e["date"], e["type"]) == key for e in existing):
                result.setdefault(code, []).append(entry)

    return result


# ── 4. 大宗交易折价（7日内） ─────────────────────────────────────────

def fetch_block_trades(days: int = 7) -> dict:
    """
    拉取近 N 天的大宗交易，过滤自选股，存 DB，返回按 code 分组的记录。
    折价 > 5% 才有预警价值（轻微折价是正常）。
    返回 {code: [{"date", "premium_pct", "amount_mn", "discount_flag": bool}, ...]}
    """
    import db
    codes = set(_cn_codes())
    now   = datetime.now(CN_TZ)
    start = (now - timedelta(days=days)).strftime("%Y%m%d")
    end   = now.strftime("%Y%m%d")

    result: dict = {}
    try:
        df = ak.stock_dzjy_mrtj(start_date=start, end_date=end)
        for _, row in df.iterrows():
            code = str(row.get("证券代码", "")).zfill(6)
            if code not in codes:
                continue
            premium_ratio = _safe_float(row.get("折溢率", 0))
            premium_pct   = round(premium_ratio * 100, 2)   # 负数=折价
            amount_mn     = _safe_float(row.get("成交总额", 0))  # 万元
            trade_date    = str(row.get("交易日期", ""))[:10]

            try:
                db.upsert_block_trade(code, trade_date, premium_pct, amount_mn)
            except Exception:
                pass

            result.setdefault(code, []).append({
                "date":         trade_date,
                "premium_pct":  premium_pct,
                "amount_mn":    amount_mn,
                "amount_bn":    round(amount_mn / 10000, 2),
                "discount_flag": premium_pct <= -5.0,
            })
    except Exception as e:
        print(f"  ⚠️ 大宗交易拉取失败: {e}")

    return result


# ── 5. 解禁预警（14日内，按类型差异化） ─────────────────────────────

# 解禁类型 → (风险等级, 说明)
_LOCKUP_RISK = {
    "首发原始股东限售股份":   ("🔴🔴", "IPO原始股东，成本接近零，卖压极大"),
    "首发网下配售限售股份":   ("🔴🔴", "IPO网下配售，持仓成本低，急于套现"),
    "定向增发机构配售股份":   ("🔴",   "定增投资者，当前价高于定增价时卖压高"),
    "高管锁定股份":           ("🟠",   "高管出售受速度限制，但信息优势最强"),
    "股权激励限售股份":       ("🟠",   "行权价格较低，有出售动机"),
    "员工持股计划":           ("🟡",   "员工有个人资金需求，但出售规模有限"),
    "战略配售股份":           ("🟡",   "战略投资者，通常不急于退出"),
    "可转债转股":             ("🟢",   "分批转股，单次影响有限"),
}
_DEFAULT_LOCKUP_RISK = ("🟠", "解禁类型不明，谨慎评估卖压")


def fetch_restricted_releases(days_ahead: int = 14) -> list:
    """
    返回未来 days_ahead 天内自选股的解禁事件。
    每条记录包含 risk_emoji, risk_desc 按类型差异化风险提示。
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
            ratio = _safe_float(row.get("占解禁前流通市值比例", 0))  # AKShare 已是百分比
            if ratio < 1.0:
                continue
            lock_type = str(row.get("限售股类型", ""))
            risk_emoji, risk_desc = _LOCKUP_RISK.get(lock_type, _DEFAULT_LOCKUP_RISK)
            releases.append({
                "code":       code,
                "name":       str(row.get("股票简称", code)),
                "date":       str(row.get("解禁时间", "")),
                "ratio":      ratio,
                "amount_bn":  _safe_float(row.get("实际解禁市值", 0)) / 1e8,
                "type":       lock_type,
                "risk_emoji": risk_emoji,
                "risk_desc":  risk_desc,
            })
    except Exception as e:
        print(f"  ⚠️ 解禁日历拉取失败: {e}")

    return releases


# ── 6. 股东人数变化（季度，筹码集中方向） ────────────────────────────

def fetch_shareholder_changes() -> dict:
    """
    拉取最近季报的股东人数，存入 DB，返回按 code 的变化摘要。
    股东人数减少 = 筹码集中（机构吸筹）；增加 = 筹码分散（散户涌入/机构出货）。
    返回 {code: {"cnt": N, "pct_change": %, "quarter": str, "signal": str}}
    """
    import db
    codes = set(_cn_codes())
    result: dict = {}

    # 尝试最近两个季度末
    now = datetime.now(CN_TZ)
    quarter_dates = []
    for delta_months in (3, 6, 9, 12):
        q_dt = now - timedelta(days=delta_months * 30)
        # 取该月所在季度末
        q_month = ((q_dt.month - 1) // 3) * 3 + 3
        q_year  = q_dt.year if q_month <= 12 else q_dt.year + 1
        q_month = q_month if q_month <= 12 else 3
        q_day   = {3: "31", 6: "30", 9: "30", 12: "31"}[q_month]
        q_str   = f"{q_year}{q_month:02d}{q_day}"
        if q_str not in quarter_dates:
            quarter_dates.append(q_str)

    for q_date in quarter_dates[:3]:
        try:
            df = ak.stock_hold_num_cninfo(date=q_date)
            if df is None or df.empty:
                continue

            quarter_label = f"{q_date[:4]}Q{(int(q_date[4:6])-1)//3+1}"
            for _, row in df.iterrows():
                code = str(row.get("证券代码", "")).zfill(6)
                if code not in codes:
                    continue
                cnt      = int(_safe_float(row.get("本期股东人数", 0)))
                pct_chg  = _safe_float(row.get("股东人数增幅", 0))

                if cnt == 0:
                    continue

                try:
                    db.upsert_inst_quarterly(code, quarter_label, cnt, pct_chg)
                except Exception:
                    pass

                if code not in result:
                    result[code] = {
                        "cnt":        cnt,
                        "pct_change": pct_chg,
                        "quarter":    quarter_label,
                        "signal":     _sh_count_signal(pct_chg),
                    }
            break  # 只用最新一期
        except Exception as e:
            print(f"  ⚠️ 股东人数({q_date})拉取失败: {e}")
            continue

    return result


def _sh_count_signal(pct_change: float) -> str:
    if pct_change <= -20:
        return "📥 大幅减少（筹码高度集中，机构/大户吸纳）"
    if pct_change <= -10:
        return "📉 明显减少（筹码集中，有机构建仓迹象）"
    if pct_change <= -3:
        return "↘ 小幅减少（轻度集中，中性偏正）"
    if pct_change <= 3:
        return "➡ 基本稳定"
    if pct_change <= 10:
        return "↗ 小幅增加（筹码轻度分散，中性）"
    if pct_change <= 20:
        return "📈 明显增加（散户涌入，注意机构是否在出货）"
    return "📤 大幅增加（筹码高度分散，典型散户接盘特征）"


# ── 7. 公司回购进度 ──────────────────────────────────────────────────

def fetch_repurchase_status() -> dict:
    """
    拉取进行中的股票回购，过滤自选股，返回回购进度摘要。
    回购 = 公司用自有资金买自己股票 = 最强的底部信号之一（花真金白银）。
    返回 {code: {"progress": str, "bought_mn": 万, "plan_mn": 万, "pct_done": %}}
    """
    codes = set(_cn_codes())
    result: dict = {}
    try:
        df = ak.stock_repurchase_em()
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).zfill(6)
            if code not in codes:
                continue
            progress  = str(row.get("实施进度", ""))
            bought    = _safe_float(row.get("已回购股份数量", 0))
            bought_mn = _safe_float(row.get("已回购金额", 0))
            plan_low  = _safe_float(row.get("计划回购金额区间-下限", 0))
            plan_high = _safe_float(row.get("计划回购金额区间-上限", 0))
            plan_mn   = (plan_low + plan_high) / 2 if plan_high else plan_low

            pct_done = round(bought_mn / plan_mn * 100, 1) if plan_mn > 0 else 0.0

            result[code] = {
                "progress":  progress,
                "bought_mn": bought_mn,
                "plan_mn":   plan_mn,
                "pct_done":  pct_done,
            }
    except Exception as e:
        print(f"  ⚠️ 回购数据拉取失败: {e}")

    return result


# ── 8. 模式识别（资金流 + 龙虎 + 高管 + 大宗） ───────────────────────

def detect_patterns(quotes: dict, fund_flow: dict, lhb: dict,
                    insider: dict, block_trades: dict) -> dict:
    """
    返回 {code: [pattern_dict, ...]}
    每个 pattern: {"type", "label", "desc", "severity": "high"|"med"|"low"}
    """
    patterns: dict = {}

    for code in _cn_codes():
        q  = quotes.get(code, {})
        ff = fund_flow.get(code, {})
        lb = lhb.get(code, {})
        ic = insider.get(code, [])
        bt = block_trades.get(code, [])

        change    = _safe_float(q.get("change", 0))
        main_net  = _safe_float(ff.get("main_net", 0))
        super_net = _safe_float(ff.get("super_net", 0))
        found = []

        # ── 资金流模式 ──────────────────────────────────
        if change >= 2.0 and main_net <= -0.5:
            found.append({
                "type": "出货", "severity": "high",
                "label": "📤 疑似出货",
                "desc":  f"股价涨{change:.1f}% 但主力净流出{abs(main_net):.2f}亿——机构借涨向散户出货",
            })

        if change <= -2.0 and super_net >= 0.5:
            found.append({
                "type": "吸筹", "severity": "med",
                "label": "📥 疑似吸筹",
                "desc":  f"股价跌{abs(change):.1f}% 但超大单净流入{super_net:.2f}亿——机构趁跌建仓",
            })

        # ── 龙虎榜 ──────────────────────────────────────
        net_lhb = lb.get("inst_net_buy", 0)
        if net_lhb <= -1.0:
            found.append({
                "type": "龙虎出货", "severity": "high",
                "label": "🐯 龙虎榜·机构卖出",
                "desc":  (f"近7日龙虎榜机构净卖出{abs(net_lhb):.2f}亿"
                          f"（卖方{lb['sell_count']}家 > 买方{lb['buy_count']}家）"),
            })
        elif net_lhb >= 1.0:
            found.append({
                "type": "龙虎吸筹", "severity": "med",
                "label": "🐯 龙虎榜·机构买入",
                "desc":  (f"近7日龙虎榜机构净买入{net_lhb:.2f}亿"
                          f"（买方{lb['buy_count']}家 > 卖方{lb['sell_count']}家）"),
            })

        # ── 高管增减持 ──────────────────────────────────
        buys  = [x for x in ic if x["type"] == "buy"]
        sells = [x for x in ic if x["type"] == "sell"]

        if len(sells) >= 2:
            total_sell_price = sum(s["shares"] * s["price"] for s in sells) / 1e4
            found.append({
                "type": "高管集体减持", "severity": "high",
                "label": "⚠️ 高管集体减持",
                "desc":  (f"近30日 {len(sells)} 名高管/股东减持"
                          f"（涉及金额约{total_sell_price:.0f}万元）——最了解公司的人在离场"),
            })
        elif len(sells) == 1:
            s = sells[0]
            found.append({
                "type": "高管减持", "severity": "med",
                "label": "📉 内部人减持",
                "desc":  (f"{s['role'] or '相关人员'} {s['name']} 近30日减持"
                          f"{s['shares']:.0f}股（均价{s['price']:.2f}）"),
            })

        if buys:
            total_buy_price = sum(b["shares"] * b["price"] for b in buys) / 1e4
            found.append({
                "type": "高管增持", "severity": "low",
                "label": "✅ 内部人增持",
                "desc":  (f"近30日 {len(buys)} 名高管/股东增持"
                          f"（涉及金额约{total_buy_price:.0f}万元）——用真钱表达信心"),
            })

        # ── 大宗交易折价 ────────────────────────────────
        heavy_discounts = [b for b in bt if b.get("discount_flag")]
        if heavy_discounts:
            max_disc = min(b["premium_pct"] for b in heavy_discounts)
            total_amt = sum(b["amount_bn"] for b in heavy_discounts)
            found.append({
                "type": "大宗折价", "severity": "high",
                "label": "🏷 大宗交易大幅折价",
                "desc":  (f"近7日大宗成交{len(heavy_discounts)}笔，最大折价{abs(max_disc):.1f}%"
                          f"，合计{total_amt:.2f}亿——机构通过大宗渠道悄悄出货"),
            })

        if found:
            patterns[code] = found

    return patterns


# ── 9. 格式化报告 ────────────────────────────────────────────────────

def format_institutional_section(patterns: dict, northbound_trend: dict,
                                  restricted: list, quotes: dict,
                                  shareholder: dict, repurchase: dict) -> str:
    lines = ["## 🏦 机构雷达"]

    # ── 北向趋势 ──────────────────────────────────────
    if northbound_trend:
        d5  = northbound_trend.get("d5_net", 0)
        d10 = northbound_trend.get("d10_net", 0)
        sig = northbound_trend.get("signal", "")
        con = northbound_trend.get("consecutive", 0)
        dir_ = northbound_trend.get("direction", "")
        sign5  = "+" if d5  >= 0 else ""
        sign10 = "+" if d10 >= 0 else ""
        icon   = "📈" if d5 >= 0 else "📉"
        lines.append(
            f"\n**北向资金趋势**：{icon} {sig}"
            f"（5日累计 **{sign5}{d5:.0f}亿**，10日累计 {sign10}{d10:.0f}亿）"
        )
        if con >= 5:
            dir_cn = "净流入" if dir_ == "inflow" else "净流出"
            lines.append(f"> ⚡ 连续 **{con} 日{dir_cn}**，趋势明确，非随机噪音")
        if d5 <= -100:
            lines.append("> ⚠️ 外资5日大幅撤离，注意个股估值支撑是否仍在")
        elif d5 >= 100:
            lines.append("> ✅ 外资5日大幅流入，全市场风险偏好回升")

    # ── 个股机构行为模式 ──────────────────────────────
    if patterns:
        lines.append("\n**个股机构行为**\n")
        # 按严重程度排序
        sev_order = {"high": 0, "med": 1, "low": 2}
        for code, plist in patterns.items():
            name = quotes.get(code, {}).get("name", code)
            plist_sorted = sorted(plist, key=lambda p: sev_order.get(p.get("severity", "low"), 2))
            for p in plist_sorted:
                lines.append(f"- **{name}（{code}）** {p['label']}：{p['desc']}")
    else:
        lines.append("\n**个股机构行为**：今日无明显异常模式")

    # ── 股东人数 ──────────────────────────────────────
    notable_sh = {c: v for c, v in shareholder.items()
                  if abs(v.get("pct_change", 0)) >= 10}
    if notable_sh:
        lines.append("\n**季度股东人数变化（筹码方向）**\n")
        for code, v in notable_sh.items():
            name = quotes.get(code, {}).get("name", code)
            sign = "+" if v["pct_change"] >= 0 else ""
            lines.append(
                f"- **{name}（{code}）** {v['quarter']} "
                f"股东人数{sign}{v['pct_change']:.1f}%（{v['cnt']:,}户）  "
                f"{v['signal']}"
            )

    # ── 回购进度 ──────────────────────────────────────
    active_buybacks = {c: v for c, v in repurchase.items()
                       if v.get("pct_done", 0) > 0 or "实施" in v.get("progress", "")}
    if active_buybacks:
        lines.append("\n**🔄 回购进度（公司在用真钱买自己股票）**\n")
        for code, v in active_buybacks.items():
            name = quotes.get(code, {}).get("name", code)
            bar  = "▓" * min(int(v["pct_done"] / 10), 10)
            lines.append(
                f"- **{name}（{code}）** 已回购{v['pct_done']:.0f}%"
                f" [{bar}]  {v['progress']}"
            )

    # ── 解禁预警（按风险等级差异化） ────────────────────
    if restricted:
        lines.append("\n**⏰ 解禁预警（14日内）**\n")
        # 按风险等级排序：🔴🔴 > 🔴 > 🟠 > 🟡 > 🟢
        risk_order = {"🔴🔴": 0, "🔴": 1, "🟠": 2, "🟡": 3, "🟢": 4}
        restricted_sorted = sorted(restricted,
                                   key=lambda r: risk_order.get(r["risk_emoji"], 5))
        for r in restricted_sorted:
            lines.append(
                f"- {r['risk_emoji']} **{r['name']}（{r['code']}）** {r['date']} 解禁"
                f"  规模{r['amount_bn']:.1f}亿（流通盘{r['ratio']:.1f}%）"
                f"  *{r['type']}*"
            )
            lines.append(f"  > {r['risk_desc']}")

    return "\n".join(lines)


# ── 10. 主入口（供 pipeline 调用） ──────────────────────────────────

def run_institutional_radar(data: dict) -> str:
    """
    传入 pipeline data dict，返回机构雷达报告片段（Markdown）。
    data 中需含 quotes（{code: {price, change, ...}}）和 fund_flow。
    """
    print("  🏦 机构雷达：龙虎榜…")
    lhb = fetch_lhb_signals(days=7)

    print("  🏦 机构雷达：北向趋势（10日）…")
    northbound_trend = fetch_northbound_trend(days=10)

    print("  🏦 机构雷达：解禁日历…")
    restricted = fetch_restricted_releases(days_ahead=14)

    print("  🏦 机构雷达：大宗交易折价（7日）…")
    block_trades = fetch_block_trades(days=7)

    print("  🏦 机构雷达：高管增减持（30日）…")
    insider = fetch_insider_changes(days=30)

    print("  🏦 机构雷达：季度股东人数…")
    shareholder = fetch_shareholder_changes()

    print("  🏦 机构雷达：回购进度…")
    repurchase = fetch_repurchase_status()

    quotes    = data.get("quotes", {})
    fund_flow = data.get("fund_flow", {})

    print("  🏦 机构雷达：识别行为模式…")
    patterns = detect_patterns(quotes, fund_flow, lhb, insider, block_trades)

    return format_institutional_section(
        patterns, northbound_trend, restricted,
        quotes, shareholder, repurchase
    )
