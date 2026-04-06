#!/usr/bin/env python3
"""
股票雷达 · 抓取层
拉个股新闻、实时行情、北向资金、龙虎榜
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, time, requests
import feedparser
from datetime import datetime
import akshare as ak
from config import (
    WATCHLIST, HK_WATCHLIST, SECTOR_KEYWORDS,
    NEWS_PER_STOCK, RAW_OUTPUT, CN_TZ
)


# ── 个股行情（新浪财经，境外IP可用）────────────────
def _sina_prefix(code: str) -> str:
    """A股代码加交易所前缀"""
    return ("sh" if code.startswith(("6", "9")) else "sz") + code

def fetch_quotes():
    """一次请求拉全部自选股行情（新浪财经接口）"""
    print("  📊 拉取行情...")
    codes   = [c for _, c, _ in WATCHLIST]
    symbols = ",".join(_sina_prefix(c) for c in codes)
    name_map = {c: n for n, c, _ in WATCHLIST}
    quotes = {}
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={symbols}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=10
        )
        for line in r.text.strip().splitlines():
            # var hq_str_sh600031="名称,今开,昨收,现价,最高,最低,..."
            if '="' not in line:
                continue
            sym  = line.split("hq_str_")[1].split("=")[0]   # sh600031
            code = sym[2:]                                    # 600031
            fields = line.split('"')[1].split(",")
            if len(fields) < 9:
                continue
            price    = float(fields[3])
            prev     = float(fields[2])
            change   = round((price - prev) / prev * 100, 2) if prev else 0.0
            amount   = float(fields[9]) / 1e8                # 元 → 亿
            name     = name_map.get(code, fields[0])
            quotes[code] = {
                "name":     name,
                "code":     code,
                "price":    price,
                "change":   change,
                "amount":   amount,
                "turnover": 0.0,   # 新浪接口无换手率，后续可补
            }
            sign = "🔴" if change >= 0 else "🟢"
            print(f"    {sign} {name}({code}) {price} ({change:+.2f}%)")
    except Exception as e:
        print(f"    ⚠️ 行情: {e}")
    return quotes


# ── 个股新闻 ──────────────────────────────────────────
def fetch_stock_news(code: str, name: str) -> list:
    try:
        df = ak.stock_news_em(symbol=code)
        items = []
        for _, row in df.head(NEWS_PER_STOCK).iterrows():
            items.append({
                "title":   row.get("新闻标题", ""),
                "summary": row.get("新闻内容", "")[:200],
                "time":    str(row.get("发布时间", "")),
                "source":  row.get("文章来源", ""),
                "link":    row.get("新闻链接", ""),
            })
        print(f"    📰 {name}: {len(items)} 条新闻")
        return items
    except Exception as e:
        print(f"    ⚠️ {name} 新闻: {e}")
        return []


# ── 个股公告 ──────────────────────────────────────────
def fetch_announcements(code: str, name: str) -> list:
    try:
        df = ak.stock_notice_report(symbol=code)
        items = []
        for _, row in df.head(3).iterrows():
            items.append({
                "title": str(row.get("公告标题", row.get("title", ""))),
                "date":  str(row.get("公告日期", row.get("date", ""))),
                "link":  str(row.get("公告链接", row.get("url", ""))),
            })
        if items:
            print(f"    📋 {name}: {len(items)} 条公告")
        return items
    except Exception as e:
        # 公告接口有时不稳定，静默失败
        return []


# ── A股财务数据（ROE / 净利率 / 负债率 + PE/PB 历史百分位）────
def fetch_cn_financials(code: str) -> dict:
    """
    拉取 A 股基本面财务数据，返回：
      - roe_trend:    近5年 ROE（年报），字符串列表
      - margin_trend: 近5年销售净利率
      - debt_trend:   近5年资产负债率
      - pe_current / pe_percentile_5y：当前PE + 5年历史百分位
      - pb_current / pb_percentile_5y：当前PB + 5年历史百分位

    数据源：同花顺年报 + 百度估值历史
    """
    result = {}
    pure = code.split(".")[0]

    # 1. 年报财务摘要（ROE/净利率/负债率/EPS/OCF）
    try:
        df = ak.stock_financial_abstract_ths(symbol=pure, indicator='按年度')
        rows = []
        for _, row in df.tail(6).iloc[::-1].iterrows():  # 最新6年，倒序
            year  = str(row.get("报告期", ""))
            if not year or year in ("False", "nan"):
                continue
            rows.append({
                "year":         year,
                "roe":          str(row.get("净资产收益率", "")),
                "net_margin":   str(row.get("销售净利率", "")),
                "gross_margin": str(row.get("销售毛利率", "")),
                "debt_ratio":   str(row.get("资产负债率", "")),
                "profit_growth":str(row.get("净利润同比增长率", "")),
                "revenue":      str(row.get("营业总收入", "")),
                "net_profit":   str(row.get("净利润", "")),
                "eps":          str(row.get("基本每股收益", "")),
                "ocf_per_share":str(row.get("每股经营现金流", "")),
                "bvps":         str(row.get("每股净资产", "")),
            })
        result["annual"] = rows
        if rows:
            latest = rows[0]
            print(f"    📊 {code} 财务: ROE={latest['roe']} 净利率={latest['net_margin']} 负债率={latest['debt_ratio']}")
    except Exception as e:
        print(f"    ⚠️ {code} 财务摘要: {e}")
        result["annual"] = []

    time.sleep(0.5)

    # 2. PE 历史百分位（百度，近5年）
    try:
        df_pe = ak.stock_zh_valuation_baidu(symbol=pure, indicator='市盈率(TTM)', period='近5年')
        df_pe = df_pe.dropna(subset=['value'])
        df_pe = df_pe[df_pe['value'] > 0]
        if not df_pe.empty:
            pe_now = round(float(df_pe['value'].iloc[-1]), 1)
            pe_pct = round(float((df_pe['value'] < pe_now).mean() * 100), 0)
            result["pe_current"]       = pe_now
            result["pe_percentile_5y"] = int(pe_pct)
            print(f"    📈 {code} PE={pe_now}x (5年 {pe_pct:.0f}%分位)")
    except Exception as e:
        print(f"    ⚠️ {code} PE历史: {e}")

    time.sleep(0.5)

    # 3. PB 历史百分位（百度，近5年）
    try:
        df_pb = ak.stock_zh_valuation_baidu(symbol=pure, indicator='市净率', period='近5年')
        df_pb = df_pb.dropna(subset=['value'])
        df_pb = df_pb[df_pb['value'] > 0]
        if not df_pb.empty:
            pb_now = round(float(df_pb['value'].iloc[-1]), 2)
            pb_pct = round(float((df_pb['value'] < pb_now).mean() * 100), 0)
            result["pb_current"]       = pb_now
            result["pb_percentile_5y"] = int(pb_pct)
            print(f"    📈 {code} PB={pb_now}x (5年 {pb_pct:.0f}%分位)")
    except Exception as e:
        print(f"    ⚠️ {code} PB历史: {e}")

    return result


# ── 高级财务：ROIC / Owner Earnings / 留存利润检验 ──────────
def fetch_cn_advanced(code: str, annual: list = None) -> dict:
    """
    从新浪财务报表拉取：
      - ROIC（投入资本回报率）= 净利润 / (股东权益 + 有息负债)
      - Owner Earnings = 经营现金流总额 - 资本开支
      - 留存利润效率 = 近5年权益增加 / 近5年净利润合计（Buffett留存利润检验近似）
    annual: fetch_cn_financials() 返回的 annual 列表，最新在前
    """
    import pandas as pd
    result = {}
    pure = code.split(".")[0]
    prefix = "sh" if pure.startswith(("6", "9")) else "sz"
    symbol = f"{prefix}{pure}"
    CAPEX_COL = "购建固定资产、无形资产和其他长期资产所支付的现金"

    def _parse_num(s, unit=1):
        """解析字符串数字，unit=1e8 表示原单位是亿"""
        try:
            v = float(str(s).replace('亿', '').replace('元', '').replace('%', '')
                              .replace('--', '').replace(',', '').strip())
            return v * unit
        except Exception:
            return None

    def _year_rows(df):
        """筛选年报行（日期以1231结尾）"""
        return df[df['报告日'].astype(str).str.endswith('1231')].reset_index(drop=True)

    try:
        bs = ak.stock_financial_report_sina(stock=symbol, symbol='资产负债表')
        cf = ak.stock_financial_report_sina(stock=symbol, symbol='现金流量表')
        bs_yr = _year_rows(bs)
        cf_yr = _year_rows(cf)
    except Exception as e:
        print(f"    ⚠️ {code} 高级财务读取失败: {e}")
        return result

    roic_list, oe_list, equity_hist = [], [], []
    annual = annual or []

    for _, bs_row in bs_yr.head(6).iterrows():
        date = str(bs_row['报告日'])
        year = date[:4]

        equity   = bs_row.get('归属于母公司股东权益合计') or 0
        st_debt  = bs_row.get('短期借款') or 0
        lt_debt  = bs_row.get('长期借款') or 0
        bonds    = bs_row.get('应付债券') or 0
        cash     = bs_row.get('货币资金') or 0
        shares_capital = bs_row.get('实收资本(或股本)') or 0  # 实收资本（元），A股=股数×1元面值

        if isinstance(bonds, float) and (bonds != bonds):  # NaN check
            bonds = 0

        ic = equity + st_debt + lt_debt + bonds - cash  # Invested Capital (元)
        equity_hist.append((year, equity))

        # 找对应年的 annual 数据
        ann = next((r for r in annual if str(r.get('year', ''))[:4] == year), None)
        if not ann:
            continue

        net_p_yi = _parse_num(ann.get('net_profit', ''))   # 亿
        eps       = _parse_num(ann.get('eps', ''))
        ocf_ps    = _parse_num(ann.get('ocf_per_share', ''))

        if net_p_yi is None or eps is None or eps == 0:
            continue

        net_p = net_p_yi * 1e8  # 亿 → 元

        # ROIC
        if ic > 1e6:  # 至少100万，避免异常
            roic = round(net_p / ic * 100, 1)
            roic_list.append({'year': year, 'roic': roic})

        # Owner Earnings = OCF - CapEx
        if ocf_ps is not None and shares_capital > 0:
            shares = shares_capital   # 元 面值，A股面值1元，所以 shares_capital = 股数（元）
            ocf_total = ocf_ps * shares  # 元
            cf_row = cf_yr[cf_yr['报告日'].astype(str).str.startswith(year)]
            if not cf_row.empty:
                capex = cf_row.iloc[0].get(CAPEX_COL) or 0
                if capex != capex: capex = 0  # NaN
                oe = ocf_total - capex
                oe_list.append({
                    'year':     year,
                    'oe_bn':    round(oe / 1e8, 2),
                    'capex_bn': round(capex / 1e8, 2),
                    'ocf_bn':   round(ocf_total / 1e8, 2),
                })

    if roic_list:
        result['roic_trend']  = roic_list
        result['roic_latest'] = roic_list[0]['roic']
        trend_str = " → ".join(f"{r['roic']}%" for r in roic_list[:4])
        print(f"    📊 {code} ROIC: {trend_str}")

    if oe_list:
        result['owner_earnings'] = oe_list
        latest = oe_list[0]
        print(f"    💰 {code} Owner Earnings: {latest['oe_bn']:.1f}亿 (OCF {latest['ocf_bn']:.1f}亿 - CapEx {latest['capex_bn']:.1f}亿)")

    # 留存利润检验（近5年）
    if len(equity_hist) >= 5 and len(annual) >= 5:
        try:
            eq_new = equity_hist[0][1]   # 最新年末股东权益（元）
            eq_old = equity_hist[4][1]   # 5年前年末
            eq_change = (eq_new - eq_old) / 1e8  # 亿

            total_np = sum(
                _parse_num(r.get('net_profit', ''))
                for r in annual[:5]
                if _parse_num(r.get('net_profit', '')) is not None
            )
            if total_np and total_np > 0:
                # 保守估计: 留存利润 ≈ 权益增加（含分红抵扣，所以是下限）
                efficiency = eq_change / total_np
                result['retained_efficiency']  = round(efficiency, 2)
                result['retained_equity_change'] = round(eq_change, 1)
                result['retained_total_profit']  = round(total_np, 1)
                quality = "优秀" if efficiency >= 1 else ("良好" if efficiency >= 0.6 else "偏低")
                print(f"    🏦 {code} 留存利润检验: {efficiency:.2f} ({quality}) 权益增{eq_change:.0f}亿/5年利润{total_np:.0f}亿")
        except Exception as e:
            print(f"    ⚠️ {code} 留存利润计算: {e}")

    return result


# ── 护城河方向自动判断 ────────────────────────────────────────
def _analyze_moat_direction(annual: list) -> str:
    """
    从年报 ROE / 净利率趋势判断护城河方向。
    annual: 最新在前，最多6年。
    返回一句话结论，用于注入 Buffett prompt。
    """
    def parse_pct(s: str):
        """解析 '8.54%' or '8.54' → float，失败返回 None"""
        try:
            return float(str(s).replace('%', '').replace('亿', '').replace('--', '').strip())
        except Exception:
            return None

    roe_vals    = [v for r in annual[:6] if (v := parse_pct(r.get('roe', ''))) is not None]
    margin_vals = [v for r in annual[:6] if (v := parse_pct(r.get('net_margin', ''))) is not None]

    if len(roe_vals) < 3:
        return ""   # 数据不够，不瞎猜

    def trend_delta(vals):
        """最近2年均值 - 最老2年均值"""
        if len(vals) < 4:
            return vals[0] - vals[-1]   # 最新 - 最旧
        return sum(vals[:2]) / 2 - sum(vals[-2:]) / 2

    roe_delta    = trend_delta(roe_vals)
    margin_delta = trend_delta(margin_vals) if len(margin_vals) >= 3 else 0
    latest_roe   = roe_vals[0]

    # 分类逻辑
    if latest_roe >= 15 and roe_delta >= 0 and margin_delta >= 0:
        direction = "护城河拓宽"
        detail    = f"ROE维持{latest_roe:.1f}%高位且上升，净利率同步改善"
    elif latest_roe >= 15 and roe_delta >= -2:
        direction = "护城河稳固"
        detail    = f"ROE {latest_roe:.1f}%，近几年波动不大"
    elif roe_delta <= -4 or (roe_delta <= -2 and margin_delta <= -2):
        direction = "护城河收窄"
        margin_note = f"净利率同步下行（{margin_vals[-1]:.1f}%→{margin_vals[0]:.1f}%）" if (margin_vals and margin_delta <= -1) else f"净利率尚稳（{margin_vals[0]:.1f}%）" if margin_vals else ""
        detail    = f"ROE从{roe_vals[-1]:.1f}%降至{latest_roe:.1f}%，{margin_note}" if margin_note else f"ROE从{roe_vals[-1]:.1f}%降至{latest_roe:.1f}%"
    elif roe_delta >= 2 and latest_roe < 15:
        direction = "护城河改善中"
        detail    = f"ROE从低位回升至{latest_roe:.1f}%，趋势向好但尚未到优质水平"
    else:
        direction = "护城河方向不明"
        detail    = f"ROE {latest_roe:.1f}%，近年变化不显著"

    return f"{direction}（{detail}）"


# ── A股特有风险/机会信号（质押 + 融资 + 机构持仓 + FCF质量）────
_pledge_cache = {}   # {date_str: DataFrame}，避免重复拉全量

def fetch_cn_signals(code: str, annual: list = None) -> dict:
    """
    投行级别信号，全部 A 股专属：
      - pledge_ratio:   大股东质押比例（%），>30% 是红旗
      - margin_trend:   融资余额近5日变化方向（+增/-减）+ 绝对金额
      - inst_change:    最近季度机构持仓变化（增持/减持/新进/退出）
      - fcf_quality:    经营现金流/净利润比率（<0.8 = 利润质量差）
    """
    result = {}
    pure = code.split(".")[0]
    is_sh = pure.startswith(("6", "9"))   # 上交所 vs 深交所

    # ── 1. 大股东质押比例 ──────────────────────────────
    try:
        global _pledge_cache
        today_key = datetime.now().strftime("%Y%m%d")
        if today_key not in _pledge_cache:
            _pledge_cache[today_key] = ak.stock_gpzy_pledge_ratio_em()
        df_pledge = _pledge_cache[today_key]
        row = df_pledge[df_pledge['股票代码'] == pure]
        if not row.empty:
            ratio = float(row.iloc[0]['质押比例'])
            result['pledge_ratio'] = ratio
            level = "⚠️ 高风险" if ratio > 40 else ("注意" if ratio > 20 else "正常")
            print(f"    🔒 {code} 质押比例: {ratio:.1f}% ({level})")
        else:
            result['pledge_ratio'] = 0.0
    except Exception as e:
        print(f"    ⚠️ {code} 质押比例: {e}")

    time.sleep(0.3)

    # ── 2. 融资余额趋势（近5个交易日）──────────────────
    try:
        from datetime import datetime as dt, timedelta
        balance_list = []
        d = dt.now()
        attempts = 0
        while len(balance_list) < 5 and attempts < 15:
            d -= timedelta(days=1)
            if d.weekday() >= 5:   # 跳过周末
                attempts += 1
                continue
            date_str = d.strftime("%Y%m%d")
            try:
                if is_sh:
                    df_m = ak.stock_margin_detail_sse(date=date_str)
                    row_m = df_m[df_m['标的证券代码'] == pure]
                else:
                    df_m = ak.stock_margin_detail_szse(date=date_str)
                    row_m = df_m[df_m['标的证券代码'] == pure] if '标的证券代码' in df_m.columns else df_m[df_m.iloc[:,0].astype(str)==pure]
                if not row_m.empty:
                    bal = float(row_m.iloc[0]['融资余额'])
                    balance_list.append((date_str, bal))
                    time.sleep(0.1)
            except Exception:
                pass
            attempts += 1

        if len(balance_list) >= 2:
            latest  = balance_list[0][1]
            oldest  = balance_list[-1][1]
            change  = latest - oldest
            pct     = change / oldest * 100 if oldest else 0
            direction = "↑增" if change > 0 else "↓减"
            result['margin_balance']     = latest
            result['margin_change']      = change
            result['margin_change_pct']  = round(pct, 2)
            result['margin_direction']   = direction
            result['margin_history']     = balance_list
            print(f"    💳 {code} 融资余额: {latest/1e8:.2f}亿 ({direction}{abs(change)/1e8:.2f}亿, {pct:+.1f}%)")
    except Exception as e:
        print(f"    ⚠️ {code} 融资余额: {e}")

    time.sleep(0.3)

    # ── 3. 机构持仓季度变化 ─────────────────────────────
    try:
        from datetime import datetime as dt
        # 最近已发布的季度：Q4=前年12月末，Q1=3月末，Q2=6月末，Q3=9月末
        now = dt.now()
        q_map = {1: f"{now.year-1}4", 2: f"{now.year}1",
                 3: f"{now.year}2", 4: f"{now.year}3",
                 5: f"{now.year}4", 6: f"{now.year+1}1"}  # fallback ladder
        quarter = q_map.get(now.month, f"{now.year-1}4")
        quarters_to_try = [quarter,
                           f"{int(quarter[:-1])-1 if quarter[-1]=='1' else quarter[:-1]}{int(quarter[-1])-1 if quarter[-1]!='1' else '4'}"]

        df_inst = None
        for q in quarters_to_try:
            try:
                df_inst = ak.stock_institute_hold_detail(stock=pure, quarter=q)
                if df_inst is not None and not df_inst.empty:
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if df_inst is not None and not df_inst.empty:
            total = len(df_inst)
            increased = (df_inst['持股比例增幅'] > 0).sum()
            decreased = (df_inst['持股比例增幅'] < 0).sum()
            new_enter  = df_inst[df_inst['持股数'] == 0].shape[0]
            # 找社保/QFII/主要公募
            top = df_inst[df_inst['持股机构类型'].isin(['基金','全国社保','QFII'])].head(5)
            result['inst_total']    = total
            result['inst_increased']= int(increased)
            result['inst_decreased']= int(decreased)
            result['inst_top'] = [
                {
                    "name":   r['持股机构简称'],
                    "type":   r['持股机构类型'],
                    "change": float(r['持股比例增幅']),
                    "ratio":  float(r.get('最新持股比例', r.get('持股比例', 0))),
                }
                for _, r in top.iterrows()
            ]
            net_signal = "增持" if increased > decreased else ("减持" if decreased > increased else "持平")
            print(f"    🏛️ {code} 机构持仓: {total}家 增{increased}/减{decreased} ({net_signal})")
    except Exception as e:
        print(f"    ⚠️ {code} 机构持仓: {e}")

    # ── 4. FCF 质量（每股经营现金流 / 基本每股收益）──────────────────
    if annual:
        fcf_ratios = []
        for row in annual[:5]:
            try:
                ocf = str(row.get('ocf_per_share', '')).replace('元','').strip()
                eps = str(row.get('eps', '')).replace('元','').strip()
                if ocf not in ('False','nan','','--') and eps not in ('False','nan','0','','--'):
                    ratio = float(ocf) / float(eps)
                    if abs(ratio) < 50:  # 过滤异常值
                        fcf_ratios.append(round(ratio, 2))
            except Exception:
                pass
        if fcf_ratios:
            avg_fcf = round(sum(fcf_ratios) / len(fcf_ratios), 2)
            result['fcf_quality_avg']  = avg_fcf
            result['fcf_quality_list'] = fcf_ratios
            quality = "良好" if avg_fcf >= 0.8 else ("偏低" if avg_fcf >= 0.5 else "差——利润质量存疑")
            print(f"    💰 {code} FCF质量: 均值{avg_fcf:.2f}x ({quality})")

    # ── 5. 护城河方向自动判断 ────────────────────────────
    if annual:
        moat_dir = _analyze_moat_direction(annual)
        if moat_dir:
            result['moat_direction'] = moat_dir
            print(f"    🏰 {code} {moat_dir}")

    return result


# ── 北向资金（陆股通）────────────────────────────────
def fetch_north_bound() -> dict:
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        today = df.iloc[0]
        result = {
            "date":         str(today.get("日期", "")),
            "sh_net":       float(today.get("沪股通净买入", 0)),   # 亿元
            "sz_net":       float(today.get("深股通净买入", 0)),
            "total_net":    float(today.get("北向资金净买入", today.get("沪深港通净买入", 0))),
        }
        sign = "📈" if result["total_net"] >= 0 else "📉"
        print(f"  {sign} 北向资金净买入: {result['total_net']:.2f} 亿")
        return result
    except Exception as e:
        print(f"  ⚠️ 北向资金: {e}")
        return {}


# ── 龙虎榜（当天涨跌幅超5%个股机构席位）────────────
def fetch_lhb(codes: list) -> list:
    """检查自选股是否上了龙虎榜"""
    try:
        df = ak.stock_lhb_detail_em(start_date=datetime.now(CN_TZ).strftime("%Y%m%d"),
                                     end_date=datetime.now(CN_TZ).strftime("%Y%m%d"))
        if df is None or df.empty:
            return []
        hits = []
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            if code in codes:
                hits.append({
                    "name":   row.get("名称", ""),
                    "code":   code,
                    "reason": row.get("上榜原因", ""),
                    "buy":    float(row.get("买入总金额", 0)) / 1e8,
                    "sell":   float(row.get("卖出总金额", 0)) / 1e8,
                })
        if hits:
            print(f"  🔔 龙虎榜命中: {[h['name'] for h in hits]}")
        return hits
    except Exception as e:
        print(f"  ⚠️ 龙虎榜: {e}")
        return []


# ── 板块新闻（政策面）────────────────────────────────
def fetch_sector_news() -> list:
    """从财联社快讯抓板块/政策相关新闻（stock_news_main_cx，境外IP可访问）"""
    try:
        df = ak.stock_news_main_cx()
        items = []
        seen = set()
        for _, row in df.iterrows():
            tag     = str(row.get("tag", ""))
            summary = str(row.get("summary", ""))
            url     = str(row.get("url", ""))
            text    = tag + summary
            if any(kw in text for kw in SECTOR_KEYWORDS):
                key = summary[:40]
                if key not in seen:
                    seen.add(key)
                    items.append({
                        "title": summary[:120],
                        "time":  "",   # 财联社接口不返回时间字段
                        "link":  url,
                    })
            if len(items) >= 8:
                break
        print(f"  📡 板块快讯: {len(items)} 条")
        return items
    except Exception as e:
        print(f"  ⚠️ 板块快讯: {e}")
        return []


# ── 大股东增减持 ──────────────────────────────────────
def fetch_insider_changes(code: str, name: str) -> list:
    """拉大股东/高管增减持公告"""
    try:
        df = ak.stock_hszg_em(symbol=code)
        if df is None or df.empty:
            return []
        items = []
        for _, row in df.head(3).iterrows():
            change_type = str(row.get("变动类型", row.get("类型", "")))
            holder      = str(row.get("股东名称", row.get("变动股东", "")))
            ratio       = str(row.get("变动比例", row.get("占总股本比例", "")))
            date_str    = str(row.get("截止日期", row.get("公告日期", "")))
            items.append({
                "holder": holder[:20],
                "type":   change_type,
                "ratio":  ratio,
                "date":   date_str[:10],
            })
        if items:
            print(f"    📋 {name} 增减持: {len(items)} 条")
        return items
    except Exception:
        return []


# ── 主力资金流向 ──────────────────────────────────────
def fetch_fund_flow(code: str, name: str) -> dict:
    """拉个股主力资金净流入（近5日）"""
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith(("6","9")) else "sz")
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        result = {
            "date":       str(latest.get("日期", ""))[:10],
            "main_net":   float(latest.get("主力净流入-净额", 0) or 0) / 1e8,
            "super_net":  float(latest.get("超大单净流入-净额", 0) or 0) / 1e8,
            "big_net":    float(latest.get("大单净流入-净额", 0) or 0) / 1e8,
            "main_ratio": float(latest.get("主力净流入-净占比", 0) or 0),
        }
        direction = "📈流入" if result["main_net"] >= 0 else "📉流出"
        print(f"    💰 {name} 主力 {direction} {abs(result['main_net']):.2f}亿")
        return result
    except Exception:
        return {}


# ── 国际信息源（Google News RSS）─────────────────────
# 每只股 / 每个板块的英文查询词
INTL_QUERIES = {
    # 个股竞争对手 & 公司本身
    "600031": [
        ("SANY Heavy Equipment earnings outlook",        "三一重工"),
        ("Caterpillar Komatsu excavator demand",         "竞品参照"),
    ],
    "300274": [
        ("SolarEdge Enphase inverter earnings results",  "竞品参照"),
        ("China solar storage export market 2026",       "阳光电源"),
    ],
    "600196": [
        ("Fosun Pharma clinical trial approval",         "复星医药"),
        ("China innovative drug FDA EMA approval",       "创新药"),
    ],
    # 板块/宏观
    "_sector": [
        ("IRA solar energy storage policy tariff",       "美国能源政策"),
        ("EU Europe renewable energy storage tender",    "欧洲储能"),
        ("China construction equipment global demand",   "工程机械出海"),
        ("China pharma drug licensing out deal",         "医药出海"),
    ],
}

def fetch_international_news() -> dict:
    """通过 Google News RSS 抓国际资讯，按股票代码分组"""
    print("  🌐 国际资讯...")
    result = {}   # code -> list of items  +  "_sector" -> list

    for key, queries in INTL_QUERIES.items():
        items = []
        seen  = set()
        for query, label in queries:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    title = entry.get("title", "")[:120]
                    link  = entry.get("link", "")
                    src   = entry.get("source", {}).get("title", "Google News")
                    pub   = entry.get("published", "")[:10]
                    key2  = title[:40]
                    if key2 not in seen:
                        seen.add(key2)
                        items.append({
                            "title":  title,
                            "label":  label,
                            "link":   link,
                            "source": src,
                            "time":   pub,
                        })
            except Exception:
                pass
            time.sleep(0.3)
        if items:
            result[key] = items
            tag = key if key == "_sector" else key
            print(f"    🌐 {tag}: {len(items)} 条国际资讯")

    return result


# ── A股财报日历 ───────────────────────────────────────
def fetch_cn_earnings_calendar(codes: list) -> list:
    """
    从东方财富获取自选股的近期财报披露日期。
    提前知道哪天出季报，巴菲特视角：重要业绩日前后是关键观察窗口。
    """
    events = []
    try:
        df = ak.stock_report_fund_em(symbol="全部", indicator="预约披露时间")
        if df is None or df.empty:
            return []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", ""))
            if code in codes:
                events.append({
                    "code":  code,
                    "name":  str(row.get("股票简称", "")),
                    "date":  str(row.get("预约披露时间", ""))[:10],
                    "type":  str(row.get("报告类型", "")),
                })
        events.sort(key=lambda x: x["date"])
        if events:
            print(f"  📅 A股财报日历: {len(events)} 只有近期财报")
    except Exception as e:
        print(f"  ⚠️ 财报日历: {e}")
    return events


# ── 主逻辑 ────────────────────────────────────────────
def main():
    now = datetime.now(CN_TZ)
    print(f"\n📈 股票雷达 抓取开始 {now.strftime('%Y-%m-%d %H:%M CST')}")

    output = {
        "date":           now.strftime("%Y-%m-%d"),
        "time":           now.isoformat(),
        "quotes":         {},
        "news":           {},
        "announcements":  {},
        "insider":        {},
        "fund_flow":      {},
        "north_bound":    {},
        "lhb":            [],
        "sector_news":    [],
        "intl_news":      {},
        "cn_earnings":    [],   # A股财报日历
    }

    # 行情
    output["quotes"] = fetch_quotes()
    time.sleep(1)

    # 个股新闻 + 公告 + 增减持 + 资金流向
    print("\n  📰 个股动态：")
    codes = [code for _, code, _ in WATCHLIST]
    for name, code, _ in WATCHLIST:
        output["news"][code]          = fetch_stock_news(code, name)
        output["announcements"][code] = fetch_announcements(code, name)
        output["insider"][code]       = fetch_insider_changes(code, name)
        output["fund_flow"][code]     = fetch_fund_flow(code, name)
        time.sleep(0.5)

    # 北向资金
    print("\n  🏦 资金面：")
    output["north_bound"] = fetch_north_bound()

    # 龙虎榜
    output["lhb"] = fetch_lhb(codes)

    # 板块快讯
    print("\n  🗞️ 板块政策快讯：")
    output["sector_news"] = fetch_sector_news()

    # 国际资讯
    print("\n  🌐 国际信息源：")
    output["intl_news"] = fetch_international_news()

    # A股财报日历
    print("\n  📅 财报日历：")
    output["cn_earnings"] = fetch_cn_earnings_calendar(codes)

    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_news = sum(len(v) for v in output["news"].values())
    print(f"\n✅ 完成：{len(output['quotes'])} 只股行情，{total_news} 条新闻，"
          f"{len(output['sector_news'])} 条板块快讯 → {RAW_OUTPUT}")


if __name__ == "__main__":
    main()
