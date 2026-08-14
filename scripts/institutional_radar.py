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

import math
import time
from datetime import datetime, timedelta

import akshare as ak

from scripts.config import CN_TZ
from scripts.northbound_status import (NB_EPSILON as _NB_EPSILON,
                                       is_northbound_stale as _is_northbound_stale)


# ── 工具 ─────────────────────────────────────────────────────────────

def _cn_codes():
    # 机构雷达喂所有用户的详情页，universe 该是全部自选 A股，
    # 不能用 get_active（仅开了每日推送的用户）——生产没人开推送时会返回 0 只、整服务空跑。
    try:
        import db
        return [code for code, _ in db.get_all_cn_watchlist_stocks()]
    except Exception:
        return []


def _safe_float(val, default=0.0):
    # NaN 也要落回 default：float(nan) 不抛异常，漏下去会在 int()/格式化处炸
    # （2026-07-15 起 monolith 连崩 10 天的根因就是回购 pct_done=NaN）
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) or math.isinf(f) else f


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
           "direction": "inflow"|"outflow"|"flat", "stale": bool, "as_of": "YYYY-MM-DD"}
    数据源停更时返回 {"stale": True, ...}，调用方必须据此把该分项判为 invalid。
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

    rows = [r for r in hist if r["total_net"] is not None]  # index0 = 最新
    if not rows:
        return {}
    nets = [r["total_net"] for r in rows]

    # US-151：数据源死活判定。官方 2026-07 起停止公布日度北向数据，
    # akshare 从那之后返回 0.0 或空。不判这一下，下面的「连续同向」会把
    # 一串 0.0 读成「连续 N 天净流入」，凭空造出看多证据。
    as_of = str(rows[0].get("date", ""))[:10]
    stale = _is_northbound_stale(as_of)
    if stale:
        return {"stale": True, "as_of": as_of, "direction": "unknown",
                "consecutive": 0, "signal": "数据源已停更"}

    d5  = sum(nets[:5])  if len(nets) >= 5  else sum(nets)
    d10 = sum(nets[:10]) if len(nets) >= 10 else sum(nets)

    # 连续同向天数。0.0 既不是流入也不是流出 —— 原来 `n >= 0` 把 0.0 算进
    # 「流入」，停更后那串 0.0 就变成了「连续 N 天买入」的假证据。
    if abs(nets[0]) < _NB_EPSILON:
        direction, consecutive = "flat", 0
    else:
        direction = "inflow" if nets[0] > 0 else "outflow"
        consecutive = 0
        for n in nets:
            if abs(n) < _NB_EPSILON:
                break
            if (direction == "inflow" and n > 0) or (direction == "outflow" and n < 0):
                consecutive += 1
            else:
                break

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
        "stale":       False,
        "as_of":       as_of,
    }


# ── 3. 高管增减持（30日内） ──────────────────────────────────────────

def fetch_insider_changes(days: int = 30) -> dict:
    """
    返回按 code 分组的高管增减持列表。
    策略：先读 DB 缓存（有30天内记录的 code 跳过网络）；网络部分限时 60 秒。
    返回 {code: [{"name", "role", "type": "buy"|"sell", "shares", "price", "date"}, ...]}
    """
    import db
    import threading
    codes = _cn_codes()
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    result: dict = {}

    # ── Step 1: DB 优先 ──
    codes_with_db = set()
    for code in codes:
        db_rows = db.get_insider_changes(code, days=days)
        if db_rows:
            codes_with_db.add(code)
            for r in db_rows:
                result.setdefault(code, []).append({
                    "name": r["holder_name"], "role": r["role"],
                    "type": r["change_type"],  "shares": r["shares"],
                    "price": r["avg_price"],   "date": r["change_date"],
                })

    missing_codes = [c for c in codes if c not in codes_with_db]
    if not missing_codes:
        return result

    # ── Step 2: 网络补齐，限时 60 秒 ──
    fetch_buf: dict = {}
    stop_flag = threading.Event()

    def _store(code, name, role, raw_type, shares, price, date_str):
        if date_str < cutoff:
            return
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
        fetch_buf.setdefault(code, []).append({
            "name": name, "role": role, "type": ctype,
            "shares": abs(_safe_float(shares)), "price": _safe_float(price),
            "date": date_str,
        })

    def _do_fetch():
        missing_set = set(missing_codes)

        # SSE（逐股，最慢——有多少做多少，超时自动停）
        for code in missing_codes:
            if stop_flag.is_set() or _exchange(code) != "sse":
                continue
            try:
                df = ak.stock_share_hold_change_sse(symbol=_pure(code))
                if df is not None:
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
            if not stop_flag.is_set():
                time.sleep(0.3)

        # SZSE（全量一次）
        szse_missing = {c for c in missing_set if _exchange(c) == "szse"}
        if szse_missing and not stop_flag.is_set():
            try:
                df = ak.stock_share_hold_change_szse(symbol="全部")
                if df is not None:
                    for _, row in df.iterrows():
                        if stop_flag.is_set():
                            break
                        code = str(row.get("证券代码", "")).zfill(6)
                        if code not in szse_missing:
                            continue
                        _store(code,
                               str(row.get("变动人姓名", row.get("姓名", ""))),
                               str(row.get("变动人与上市公司的关系", row.get("职务", ""))),
                               str(row.get("变动类型", row.get("变动原因", ""))),
                               row.get("变动股份数量", row.get("变动数", 0)),
                               row.get("变动均价", row.get("本次变动平均价格", 0)),
                               str(row.get("变动截止日期", row.get("变动日期", "")))[:10])
            except Exception:
                pass

        # BSE（逐股）
        for code in missing_codes:
            if stop_flag.is_set() or _exchange(code) != "bse":
                continue
            try:
                df = ak.stock_share_hold_change_bse(symbol=_pure(code))
                if df is not None:
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
            if not stop_flag.is_set():
                time.sleep(0.3)

    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    t.join(timeout=60)
    stop_flag.set()

    result.update(fetch_buf)
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

def _quarter_dates_to_try() -> list:
    """返回最近3个季度末日期字符串列表，格式 YYYYMMDD。"""
    now = datetime.now(CN_TZ)
    seen, result = set(), []
    for delta_months in (3, 6, 9, 12):
        q_dt    = now - timedelta(days=delta_months * 30)
        q_month = ((q_dt.month - 1) // 3) * 3 + 3
        q_year  = q_dt.year
        q_day   = {3: "31", 6: "30", 9: "30", 12: "31"}[q_month]
        q_str   = f"{q_year}{q_month:02d}{q_day}"
        if q_str not in seen:
            seen.add(q_str)
            result.append(q_str)
    return result[:3]


def fetch_shareholder_changes() -> dict:
    """
    返回按 code 的最新季度股东人数变化。
    stock_hold_num_cninfo 内部逐股请求约 6000 次，极慢（~2h）。
    策略：优先读 DB 缓存（45天内的季度数据）；DB 缺失时才调 AKShare，且限时 90 秒。
    返回 {code: {"cnt": N, "pct_change": %, "quarter": str, "signal": str}}
    """
    import db
    import threading
    codes = set(_cn_codes())
    result: dict = {}

    # ── Step 1: 从 DB 读缓存 ──
    for code in codes:
        row = db.get_inst_quarterly(code)
        if row and row.get("quarter"):
            result[code] = {
                "cnt":        row["shareholder_cnt"],
                "pct_change": row["sh_pct_change"],
                "quarter":    row["quarter"],
                "signal":     _sh_count_signal(row["sh_pct_change"]),
            }

    missing = codes - set(result.keys())
    if not missing:
        return result  # 全命中缓存，跳过网络调用

    # ── Step 2: 尝试网络补齐缺失的 codes，限时 90 秒 ──
    fetch_buf: dict = {}
    fetch_done = threading.Event()

    def _do_fetch():
        for q_date in _quarter_dates_to_try():
            if fetch_done.is_set():
                break
            try:
                df = ak.stock_hold_num_cninfo(date=q_date)
                if df is None or df.empty:
                    continue
                quarter_label = f"{q_date[:4]}Q{(int(q_date[4:6])-1)//3+1}"
                for _, row in df.iterrows():
                    if fetch_done.is_set():
                        break
                    code = str(row.get("证券代码", "")).zfill(6)
                    if code not in missing or code in fetch_buf:
                        continue
                    cnt     = int(_safe_float(row.get("本期股东人数", 0)))
                    pct_chg = _safe_float(row.get("股东人数增幅", 0))
                    if cnt == 0:
                        continue
                    try:
                        db.upsert_inst_quarterly(code, quarter_label, cnt, pct_chg)
                    except Exception:
                        pass
                    fetch_buf[code] = {
                        "cnt":        cnt,
                        "pct_change": pct_chg,
                        "quarter":    quarter_label,
                        "signal":     _sh_count_signal(pct_chg),
                    }
                break  # 只用最新一期
            except Exception as e:
                print(f"  ⚠️ 股东人数({q_date})拉取失败: {e}")
                continue

    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    t.join(timeout=90)
    fetch_done.set()  # 通知线程退出（若还在跑）

    result.update(fetch_buf)
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


# ── 8b. 机构意向综合评分 ─────────────────────────────────────────────

import math as _math

_INTENTION_WEIGHTS = {
    # ── 已发生行为（US-66）──────────────────────────────────────────
    "insider":       2.0,  # 高管净操作 — 花真钱，信息优势最强
    "northbound":    1.5,  # 北向趋势 — 外资机构，信息质量高
    "lhb":           1.5,  # 龙虎榜净买卖 — 主动操作记录
    "block":         1.0,  # 大宗方向 — 折价=出货 溢价=建仓
    "shareholder":   1.0,  # 股东人数趋势 — 筹码方向（滞后但可靠）
    "fund_flow":     0.5,  # 资金流vs价格背离 — 今日噪音多
    "repurchase":    0.5,  # 回购进度 — 锦上添花
    # ── 前兆信号（US-67）— 比行为早 1-4 周 ────────────────────────
    "survey":        1.5,  # 机构调研热度 — 机构专程来看 = 有明确兴趣
    "short_selling": 1.0,  # 融券余量变化 — 聪明钱在借券做空
    "participation": 0.7,  # 机构参与度异常 — 机构今天特别活跃
}

_PHASE_TABLE = [
    ( 5.0,  10.0, "聪明钱在大量买入",   "🟢", "strong_buy"),
    ( 2.0,   5.0, "有机构在悄悄建仓",   "🟡", "mild_buy"),
    (-2.0,   2.0, "机构暂无明显动向",   "⚪", "neutral"),
    (-5.0,  -2.0, "机构在陆续减持",     "🟠", "mild_sell"),
    (-10.0, -5.0, "聪明钱在加速离场",   "🔴", "strong_sell"),
]


def _tanh_norm(x: float, scale: float) -> float:
    return _math.tanh(x / scale) if scale else 0.0


# ── 信号"这是什么"解释文字 ─────────────────────────────────────────────
_SIGNAL_CONTEXT = {
    "insider":       "高管是最了解公司内部情况的人。他们用自己的钱买卖自家股票，历来被认为参考价值最高。",
    "northbound":    "境外机构通过沪深港通买A股的资金。这些机构研究流程严格，被认为视野更长远。",
    "lhb":           "龙虎榜是交易所公布的成交量异常股票，榜上的机构席位代表有据可查的大额买卖记录。",
    "block":         "大宗交易是超过一定金额的大额股票协议成交。折价成交说明卖方急着离场；溢价说明买方主动找上门。",
    "shareholder":   "每季度股东人数变化揭示筹码方向——股东减少说明筹码在向少数人集中，通常是大资金在悄悄收货。",
    "fund_flow":     "主力资金是指大额买卖单，通常来自机构或大户。价格和资金流向相反时，才是真正有意思的信号。",
    "repurchase":    "公司用自己的钱从市场上买回自家股票——这是管理层用行动表达「我们认为股价被低估了」。",
    "survey":        "机构不会无缘无故花时间调研——调研密度高，通常说明他们在认真考虑，在做买入前的功课。",
    "short_selling": "融券就是借股票来卖，押注股价会跌。使用融券的主要是有判断力的专业资金，因为成本很高，散户不会用。",
    "participation": "机构参与度是当天机构交易占全市场成交的比例——数值越高，说明今天大资金越活跃。",
}


def _classify_inst_sellers(inst_top: list) -> dict:
    """区分 ETF/指数基金（被动）vs 主动管理基金的增减持方向。"""
    _PASSIVE_KW = ["ETF", "指数", "沪深300", "中证500", "上证50", "科创50",
                   "创业板", "LOF", "中证1000", "北证50", "QDII"]
    etf_sellers, active_sellers, etf_buyers, active_buyers = [], [], [], []
    for inst in (inst_top or []):
        name = inst.get("name", "")
        change = inst.get("change") or 0
        is_passive = any(kw in name for kw in _PASSIVE_KW)
        if change < -0.001:
            (etf_sellers if is_passive else active_sellers).append(inst)
        elif change > 0.001:
            (etf_buyers if is_passive else active_buyers).append(inst)
    return {"etf_sellers": etf_sellers, "active_sellers": active_sellers,
            "etf_buyers": etf_buyers, "active_buyers": active_buyers}


def _build_observations(comps: dict, precursor_raw: dict,
                         inst_class: dict, signals: dict) -> list:
    """生成"综合来看"观察列表——只陈述事实和情境，不下结论。"""
    obs = []
    etf_s  = inst_class.get("etf_sellers", [])
    act_s  = inst_class.get("active_sellers", [])
    inc    = int(signals.get("inst_increased") or 0)
    dec    = int(signals.get("inst_decreased") or 0)

    # 1. 减持主体性质
    if dec > 0:
        if etf_s and not act_s:
            obs.append(
                f"减持的主要是指数基金（如{etf_s[0]['name']}）"
                "——这类基金在指数权重调整时被动卖出，通常不代表主动判断改变"
            )
        elif act_s:
            names = "、".join(s["name"] for s in act_s[:2])
            obs.append(
                f"主动管理基金（{names}）在减持——这是基金经理主动决策，而非机械调仓"
            )

    # 2. 减持 + 同期调研 的组合
    sv_events = (precursor_raw.get("survey") or {}).get("events", [])
    has_specific = any(e.get("is_specific") for e in sv_events)
    if sv_events and dec > inc:
        note = "（包括专程拜访）" if has_specific else ""
        obs.append(
            f"值得注意：机构在减持的同时，近期仍有机构来公司调研{note}"
            "——两件事同时发生，值得自己想想各自的含义"
        )
    elif sv_events and inc == 0 and dec == 0:
        obs.append("近期有机构调研，但持仓暂无变化——可能仍在评估阶段，尚未形成买入行动")

    # 3. 融券动向
    short = precursor_raw.get("short_selling") or {}
    if short.get("valid"):
        chg = _safe_float(short.get("change_pct", 0))
        if abs(chg) < 10:
            obs.append("目前没有明显的融券做空加仓——专业资金暂时没有在押注这只股票会跌")
        elif chg >= 30:
            obs.append(
                f"融券余量增加了{chg:.0f}%——有专业资金在借券押注股价下跌，这个信号值得认真对待"
            )
        elif chg <= -30:
            obs.append(
                f"融券余量减少了{abs(chg):.0f}%——之前做空的资金在撤退（空头平仓），这有时出现在底部附近"
            )

    # 4. 高管动向
    insider = comps.get("insider", {})
    if insider.get("valid"):
        d = insider.get("dir", 0)
        if abs(d) < 0.1:
            obs.append("近30天高管没有增减持操作——最了解公司的人保持观望")
        elif d > 0.3:
            obs.append("高管在用自己的钱增持自家股票——最了解公司的人在表态")
        elif d < -0.3:
            obs.append("高管在减持自家股票——这是所有信号里权重最高的一个，值得认真看待")

    # 5. 北向有效性说明
    nb = comps.get("northbound", {})
    if not nb.get("valid") or abs(nb.get("dir", 0)) < 0.1:
        obs.append("北向资金今日方向不明确，此信号本次不纳入主要判断")

    return obs


def compute_intention_score(code: str, lhb: dict, northbound: dict,
                             insider_all: dict, block_trades: dict,
                             shareholder: dict, repurchase: dict,
                             fund_flow: dict, quotes: dict,
                             precursor: dict = None) -> dict:
    """
    返回单只股票的机构意向综合评分。
    score: -10 ~ +10（正=吸货方向，负=出货方向）
    precursor: fetch_precursor_signals() 的返回值（可选）
    """
    comps = {}  # key → {dir, weight, desc, plain_desc, valid}

    # ── 已发生行为信号 ────────────────────────────────────────────────

    # ── 1. 高管净操作 (weight 2.0) ──────────────────────
    # 为什么权重最高：高管是公司内部人，用自己的钱买卖，
    # 他们比任何人都更清楚公司未来的情况。
    ic = insider_all.get(code, [])
    buys  = [x for x in ic if x.get("type") == "buy"]
    sells = [x for x in ic if x.get("type") == "sell"]
    buy_amt  = sum(b["shares"] * b["price"] for b in buys)  / 1e4
    sell_amt = sum(s["shares"] * s["price"] for s in sells) / 1e4
    net_amt  = buy_amt - sell_amt
    dir_v = _tanh_norm(net_amt, 500)
    if net_amt > 0:
        desc = (f"公司高管用自己的钱买了{buy_amt:.0f}万元自家股票"
                f"——内部人花真金白银，说明他们看好")
    elif net_amt < 0:
        desc = (f"公司高管卖出了{sell_amt:.0f}万元自家股票"
                f"——最了解公司的人在离场，要注意")
    else:
        desc = "高管近30天没有增持也没有减持，保持中性"
    comps["insider"] = {"dir": dir_v, "weight": 2.0, "desc": desc, "valid": True}

    # ── 2. 北向资金趋势 (weight 1.5) ─────────────────────
    # 北向资金 = 外资通过沪深港通买入 A 股的资金。
    # 外资机构普遍有更严格的研究流程，连续方向比单日更可靠。
    nb  = northbound or {}
    con = nb.get("consecutive", 0)
    dir_nb = nb.get("direction", "")
    # US-151：数据源停更 / 压根没传进来 → 判 invalid，整项退出加权平均
    # （分子分母同时剔除，跟 participation 的处理一致），而不是按 0 分投票。
    # 原来这里恒 valid=True，造成两个方向相反的失真：
    #   批量链路 一串 0.0 被读成「连续买入」→ 每只 A 股白送 +1.07 分
    #   实时链路 northbound 恒为 {} → 按 0 分参与平均 → 所有 A 股意向分被稀释 ~13%
    if not nb or nb.get("stale") or dir_nb in ("", "unknown"):
        as_of = nb.get("as_of") or ""
        desc  = ("北向资金已于 2026-07 起停止公布日度数据"
                 + (f"（最后数据 {as_of}）" if as_of else "")
                 + "，本项不参与评分")
        comps["northbound"] = {"dir": 0.0, "weight": 1.5, "desc": desc, "valid": False}
    elif con and dir_nb in ("inflow", "outflow"):
        sign = +1 if dir_nb == "inflow" else -1
        dir_v = sign * min(con / 5.0, 1.0)
        if sign > 0:
            desc = (f"外资已连续{con}天买入（北向资金持续流入）"
                    f"——境外机构在建仓，通常比散户看得更远")
        else:
            desc = (f"外资已连续{con}天卖出（北向资金持续流出）"
                    f"——境外机构在撤退，值得警惕")
        comps["northbound"] = {"dir": dir_v, "weight": 1.5, "desc": desc, "valid": True}
    else:
        comps["northbound"] = {"dir": 0.0, "weight": 1.5,
                               "desc": "外资近期买卖方向不明确，处于观望状态",
                               "valid": True}

    # ── 3. 龙虎榜净买卖 (weight 1.5) ─────────────────────
    # 龙虎榜 = 交易所公布的当日成交量异常股票，
    # 榜上的机构席位代表真实的大额买卖记录。
    lb      = lhb.get(code)
    net_lhb = lb.get("inst_net_buy", 0) if lb else 0.0
    dir_v   = _tanh_norm(net_lhb, 2.0)
    if net_lhb > 0.1:
        desc = (f"过去7天机构在交易所榜单上净买入{net_lhb:.1f}亿"
                f"——有大机构在主动进货，留下了公开记录")
    elif net_lhb < -0.1:
        desc = (f"过去7天机构在交易所榜单上净卖出{abs(net_lhb):.1f}亿"
                f"——有大机构在公开渠道出货，信号明确")
    else:
        desc = "过去7天没有上龙虎榜，没有异常的大额机构操作"
    comps["lhb"] = {"dir": dir_v, "weight": 1.5, "desc": desc, "valid": True}

    # ── 4. 大宗交易方向 (weight 1.0) ─────────────────────
    # 大宗交易 = 超过一定金额的股票单独谈价成交，
    # 折价说明卖方急着出手，溢价说明买方主动上门。
    bt    = block_trades.get(code, [])
    prems = [b.get("premium_pct", 0) for b in bt if b.get("premium_pct") is not None]
    if prems:
        avg = sum(prems) / len(prems)
        dir_v = _tanh_norm(avg, 3.0)
        if avg < -2:
            desc = (f"大宗交易以低于市价{abs(avg):.1f}%成交"
                    f"——有人宁愿便宜卖，说明急着套现离场")
        elif avg > 2:
            desc = (f"大宗交易以高于市价{avg:.1f}%成交"
                    f"——有人愿意多付钱买，说明看好后市")
        else:
            desc = "大宗交易价格与市价接近，买卖双方没有明显急迫性"
    else:
        dir_v, desc = 0.0, "近7天没有大宗交易记录"
    comps["block"] = {"dir": dir_v, "weight": 1.0, "desc": desc, "valid": True}

    # ── 5. 股东人数趋势 (weight 1.0) ─────────────────────
    # 股东人数减少 = 筹码在向少数大户集中，往往是机构在悄悄买；
    # 股东人数增加 = 筹码在向散户扩散，往往是大户在分批卖出。
    sh  = shareholder.get(code)
    pct = sh.get("pct_change") if sh else None
    if pct is not None:
        dir_v = _tanh_norm(-pct, 10.0)
        if pct < -5:
            desc = (f"这季度股东人数减少了{abs(pct):.1f}%"
                    f"——股票在向少数人集中，通常是大资金在慢慢收货")
        elif pct > 5:
            desc = (f"这季度股东人数增加了{pct:.1f}%"
                    f"——越来越多散户进场接货，要注意大户是否在出手")
        else:
            desc = f"这季度股东人数基本没变（{pct:+.1f}%），筹码格局稳定"
        comps["shareholder"] = {"dir": dir_v, "weight": 1.0, "desc": desc, "valid": True}
    else:
        comps["shareholder"] = {"dir": 0.0, "weight": 1.0,
                                 "desc": "暂时没有最新季度数据", "valid": False}

    # ── 6. 资金流 vs 价格背离 (weight 0.5) ───────────────
    # 价格和资金方向相反才有意义，同向只是正常交易。
    # 跌的时候有大单进来 = 机构趁低吸纳；涨的时候主力在跑 = 借涨出货。
    ff     = fund_flow.get(code, {})
    q      = quotes.get(code, {})
    change = _safe_float(q.get("change", 0))
    main_n = _safe_float(ff.get("main_net", 0))
    sup_n  = _safe_float(ff.get("super_net", 0))
    if ff and q:
        if change <= -1.0 and sup_n >= 0.3:
            dir_v = _tanh_norm(sup_n / max(abs(change), 0.5), 0.5)
            desc  = (f"今天股价跌了{abs(change):.1f}%，但有{sup_n:.2f}亿超大单在逆势买入"
                     f"——有人在趁别人恐慌时悄悄抄底")
        elif change >= 1.0 and main_n <= -0.3:
            dir_v = -_tanh_norm(abs(main_n) / max(change, 0.5), 0.5)
            desc  = (f"今天股价涨了{change:.1f}%，但主力资金净流出{abs(main_n):.2f}亿"
                     f"——借着上涨的势头把货甩给追涨的人")
        else:
            dir_v, desc = 0.0, "今天资金流向和股价方向一致，没有异常背离"
        comps["fund_flow"] = {"dir": dir_v, "weight": 0.5, "desc": desc, "valid": True}
    else:
        comps["fund_flow"] = {"dir": 0.0, "weight": 0.5,
                               "desc": "今日资金流数据暂缺", "valid": False}

    # ── 7. 回购进度 (weight 0.5) ──────────────────────────
    # 公司回购 = 公司用自己的钱从市场上买回自己的股票注销，
    # 执行进度越高说明公司越认真，不是光说不练。
    rp       = repurchase.get(code)
    pct_done = _safe_float(rp.get("pct_done")) if rp else 0.0
    if rp and pct_done > 0:
        dir_v = min(pct_done / 100.0, 1.0)
        desc  = (f"公司正在执行回购计划，已完成{pct_done:.0f}%"
                 f"——公司用自己的真金白银从市场上买自家股票")
    else:
        dir_v, desc = 0.0, "目前没有进行中的股票回购计划"
    comps["repurchase"] = {"dir": dir_v, "weight": 0.5, "desc": desc, "valid": True}

    # ── 前兆信号（比行为早 1-4 周）────────────────────────────────────

    pc = (precursor or {}).get(code, {})

    # ── 8. 机构调研热度 (weight 1.5) ─────────────────────
    # 机构调研 = 基金经理/分析师专程去公司实地考察或预约电话。
    # 他们不会无缘无故花时间，调研密度高 = 正在做买入前的功课。
    sv = pc.get("survey", {})
    sv_score = _safe_float(sv.get("score", 0))
    if sv_score > 0:
        has_specific = any(e.get("is_specific") for e in sv.get("events", []))
        dir_v = min(sv_score / 30.0, 1.0)  # 30分以上 → 满分
        if has_specific:
            desc = sv.get("desc", f"近期有机构专程来调研（热度分{sv_score:.0f}）")
        else:
            desc = sv.get("desc", f"近期有机构参加业绩会（热度分{sv_score:.0f}）")
            dir_v *= 0.4  # 业绩说明会含金量低，打折
        comps["survey"] = {"dir": dir_v, "weight": 1.5, "desc": desc, "valid": True}
    else:
        comps["survey"] = {"dir": 0.0, "weight": 1.5,
                           "desc": "近期没有机构调研记录", "valid": True}

    # ── 9. 融券余量变化 (weight 1.0) ─────────────────────
    # 融券 = 借股票来卖，赌股票会跌。成本很高（利息+借券费），
    # 散户不用这个，用的都是有判断的专业资金。
    short = pc.get("short_selling", {})
    if short.get("valid"):
        chg = _safe_float(short.get("change_pct", 0))
        dir_v = -_tanh_norm(chg, 40.0)  # 增加做空 → 负向; 平仓 → 正向
        trend = short.get("trend", "中性")
        if trend == "做空增加":
            desc = (f"专业资金借券做空的量增加了{abs(chg):.0f}%"
                    f"——有聪明钱在赌这只股票会跌，需要留意")
        elif trend == "做空减少":
            desc = (f"之前做空的资金减少了{abs(chg):.0f}%（空头在平仓）"
                    f"——认为会跌的人开始认输撤退，可能是底部信号")
        else:
            desc = f"做空资金规模基本稳定（变化{chg:+.0f}%），没有明显的做空加仓动作"
        comps["short_selling"] = {"dir": dir_v, "weight": 1.0, "desc": desc, "valid": True}
    else:
        comps["short_selling"] = {"dir": 0.0, "weight": 1.0,
                                   "desc": "融券数据暂缺（可能不是融券标的）",
                                   "valid": False}

    # ── 10. 机构参与度异常 (weight 0.7) ──────────────────
    # 机构参与度 = 东方财富统计的当日机构交易占比。
    # 异常高 = 机构今天特别活跃；结合价格看才知道是在买还是在卖。
    # 数据显示：高参与度当日平均次日小幅下跌，所以异常高位是轻度预警。
    part = pc.get("participation", {})
    if part.get("valid"):
        trend_p = part.get("trend", "中性")
        spike   = part.get("spike", False)
        latest  = _safe_float(part.get("latest", 0))
        avg     = _safe_float(part.get("avg_30d", 0))
        recent_5 = _safe_float(part.get("recent_5", latest))
        prev_5   = _safe_float(part.get("prev_5", avg))
        if spike:
            dir_v = -0.3  # 异常高位 = 轻度预警（历史数据显示次日易回调）
            desc  = part.get("desc", f"今天机构交易异常活跃（参与度{latest:.0f}，均值{avg:.0f}）——方向不明")
        elif trend_p == "上升":
            dir_v = +0.2
            desc  = part.get("desc", f"近5天机构参与度上升（{prev_5:.0f}→{recent_5:.0f}）——机构越来越关注这只股票")
        elif trend_p == "下降":
            dir_v = -0.2
            desc  = part.get("desc", f"近5天机构参与度下降（{prev_5:.0f}→{recent_5:.0f}）——机构关注度减退")
        else:
            dir_v = 0.0
            desc  = part.get("desc", f"机构参与度平稳（当前{latest:.0f}，均值{avg:.0f}）")
        comps["participation"] = {"dir": dir_v, "weight": 0.7, "desc": desc, "valid": True}
    else:
        comps["participation"] = {"dir": 0.0, "weight": 0.7,
                                   "desc": "机构参与度数据暂缺", "valid": False}

    # ── 综合计算 ──────────────────────────────────────────
    valid   = {k: v for k, v in comps.items() if v["valid"]}
    w_sum   = sum(v["dir"] * v["weight"] for v in valid.values())
    w_max   = sum(v["weight"] for v in valid.values())
    score   = round(w_sum / w_max * 10.0, 1) if w_max else 0.0
    conf    = len(valid) / len(comps)

    # 阶段标签
    phase, emoji, phase_key = "机构暂无明显动向", "⚪", "neutral"
    for lo, hi, label, em, key in _PHASE_TABLE:
        if lo <= score < hi or (score >= 5.0 and hi == 10.0) or (score <= -5.0 and lo == -10.0):
            phase, emoji, phase_key = label, em, key
            break

    conf_label = "高" if conf >= 0.7 else ("中" if conf >= 0.4 else "低")

    # 一句话依据：取贡献最大的前2个信号
    top2 = sorted(
        [(k, v) for k, v in valid.items() if abs(v["dir"]) > 0.1],
        key=lambda x: abs(x[1]["dir"] * x[1]["weight"]),
        reverse=True,
    )[:2]
    if top2:
        evidence = "主要依据：" + " + ".join(v["desc"] for _, v in top2)
    else:
        evidence = f"{len(valid)}个有效信号均无明显倾向，当前中性"

    # 给每个信号附上"这是什么"解释
    for k, ctx in _SIGNAL_CONTEXT.items():
        if k in comps:
            comps[k]["context"] = ctx

    # 分类持仓机构
    inst_top = (shareholder.get(code) or {}).get("inst_top") if isinstance(
        shareholder.get(code), dict) else []
    # inst_top 通常在 signals 里；这里 fallback 为空
    inst_class = _classify_inst_sellers(inst_top)

    # 构建观察列表
    pc_raw = (precursor or {}).get(code, {})
    precursor_raw_for_obs = {
        "survey":        pc_raw.get("survey", {}),
        "short_selling": pc_raw.get("short_selling", {}),
        "participation": pc_raw.get("participation", {}),
    }
    # signals 快照（inst_increased/decreased 来自 shareholder 参数携带）
    sh_entry = shareholder.get(code) or {}
    signals_snap = {
        "inst_increased": sh_entry.get("inc", 0),
        "inst_decreased": sh_entry.get("dec", 0),
    }
    observations = _build_observations(comps, precursor_raw_for_obs, inst_class, signals_snap)

    return {
        "score":             score,
        "phase":             phase,
        "phase_emoji":       emoji,
        "phase_key":         phase_key,
        "confidence":        round(conf, 2),
        "confidence_label":  conf_label,
        "evidence":          evidence,
        "components":        comps,
        "valid_signal_count": len(valid),
        "inst_classification": inst_class,
        "observations":      observations,
    }


# ── 9. 格式化报告 ────────────────────────────────────────────────────

def format_institutional_section(patterns: dict, northbound_trend: dict,
                                  restricted: list, quotes: dict,
                                  shareholder: dict, repurchase: dict,
                                  intention_scores: dict = None) -> str:
    lines = ["## 🏦 机构雷达"]

    # ── 机构意向总览表（LLM 最先看到的摘要） ─────────────
    if intention_scores:
        lines.append("\n**机构意向总览**\n")
        lines.append("| 股票 | 机构在做什么 | 评分 | 置信度 |")
        lines.append("|------|-------------|------|--------|")
        for code, sc in sorted(intention_scores.items(),
                                key=lambda x: x[1]["score"], reverse=True):
            name = quotes.get(code, {}).get("name", code)
            sign = "+" if sc["score"] > 0 else ""
            lines.append(
                f"| {name}（{code}） "
                f"| {sc['phase_emoji']} {sc['phase']} "
                f"| {sign}{sc['score']} "
                f"| {sc['confidence_label']} |"
            )
        lines.append("")

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
    all_codes = set(patterns.keys()) | (set(intention_scores.keys()) if intention_scores else set())
    if all_codes:
        lines.append("\n**个股机构行为详情**\n")
        sev_order = {"high": 0, "med": 1, "low": 2}
        # 按意向分从高到低排序（出货靠前警示）
        sorted_codes = sorted(
            all_codes,
            key=lambda c: (intention_scores or {}).get(c, {}).get("score", 0),
        )
        for code in sorted_codes:
            name  = quotes.get(code, {}).get("name", code)
            sc    = (intention_scores or {}).get(code)
            plist = patterns.get(code, [])

            if sc:
                sign = "+" if sc["score"] > 0 else ""
                lines.append(
                    f"**{name}（{code}）** {sc['phase_emoji']} {sc['phase']}"
                    f"（评分 {sign}{sc['score']}，置信度：{sc['confidence_label']}）"
                )
                lines.append(f"> {sc['evidence']}")
            else:
                lines.append(f"**{name}（{code}）**")

            if plist:
                plist_sorted = sorted(plist, key=lambda p: sev_order.get(p.get("severity", "low"), 2))
                for p in plist_sorted:
                    lines.append(f"  - {p['label']}：{p['desc']}")
            lines.append("")
    else:
        lines.append("\n**个股机构行为**：今日无明显异常模式")

    # ── 股东人数 ──────────────────────────────────────
    notable_sh = {c: v for c, v in shareholder.items()
                  if abs(_safe_float(v.get("pct_change"))) >= 10}
    if notable_sh:
        lines.append("\n**季度股东人数变化（筹码方向）**\n")
        for code, v in notable_sh.items():
            name = quotes.get(code, {}).get("name", code)
            pct  = _safe_float(v.get("pct_change"))
            sign = "+" if pct >= 0 else ""
            lines.append(
                f"- **{name}（{code}）** {v['quarter']} "
                f"股东人数{sign}{pct:.1f}%（{v['cnt']:,}户）  "
                f"{v['signal']}"
            )

    # ── 回购进度 ──────────────────────────────────────
    active_buybacks = {c: v for c, v in repurchase.items()
                       if _safe_float(v.get("pct_done")) > 0 or "实施" in v.get("progress", "")}
    if active_buybacks:
        lines.append("\n**🔄 回购进度（公司在用真钱买自己股票）**\n")
        for code, v in active_buybacks.items():
            name = quotes.get(code, {}).get("name", code)
            pct  = _safe_float(v.get("pct_done"))
            bar  = "▓" * min(int(pct / 10), 10)
            lines.append(
                f"- **{name}（{code}）** 已回购{pct:.0f}%"
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

def run_institutional_radar(data: dict, budget_min: float = None) -> str:
    """
    传入 pipeline data dict，返回机构雷达报告片段（Markdown）。
    data 中需含 quotes（{code: {price, change, ...}}）和 fund_flow。

    budget_min（US-139）：前兆信号逐只循环的时间预算。到点抓多少算多少，
    自己停干净、留下 service_runs 记录，别等 GHA timeout SIGKILL。
    """
    deadline = time.time() + budget_min * 60 if budget_min else None
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

    print("  🏦 机构雷达：前兆信号（调研热度 + 融券 + 参与度）…")
    try:
        from scripts.precursor_signals import fetch_precursor_signals
        precursor = fetch_precursor_signals(_cn_codes(), deadline=deadline)
    except Exception as e:
        print(f"  ⚠️ 前兆信号拉取失败，跳过: {e}")
        precursor = {}

    print("  🏦 机构雷达：计算机构意向综合评分…")
    intention_scores = {
        code: compute_intention_score(
            code, lhb, northbound_trend, insider, block_trades,
            shareholder, repurchase, fund_flow, quotes,
            precursor=precursor,
        )
        for code in _cn_codes()
    }

    return format_institutional_section(
        patterns, northbound_trend, restricted,
        quotes, shareholder, repurchase,
        intention_scores=intention_scores,
    )
