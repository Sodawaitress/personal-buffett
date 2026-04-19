"""基金/ETF 数据获取层（AKShare）— 供 pipeline 调用。"""
from __future__ import annotations

import time
from typing import List, Optional

from scripts.fund_rater import FundData, FundSubtype, classify_fund


def fetch_fund_data(code: str, name: str, existing_cn_codes: List[str] | None = None) -> FundData:
    """
    尝试从 AKShare 获取基金详情；任何字段获取失败则留 None，评分器有缺省处理。
    """
    subtype = classify_fund(name)
    data = FundData(
        code=code,
        name=name,
        subtype=subtype,
        existing_cn_codes=existing_cn_codes or [],
    )

    # 路由到对应数据源
    if subtype in (FundSubtype.BROAD_ETF, FundSubtype.SECTOR_ETF):
        _fetch_etf(data)
    else:
        _fetch_oef(data)

    return data


# ── ETF（交易所）────────────────────────────────────────

def _fetch_etf(data: FundData):
    """从 fund_etf_spot_em + fund_etf_fund_info_em 填充。"""
    try:
        import akshare as ak

        # 实时行情（含溢折价、规模、成交额）
        spot = ak.fund_etf_spot_em()
        code_col = next((c for c in spot.columns if "代码" in c), spot.columns[0])
        name_col = next((c for c in spot.columns if "名称" in c), spot.columns[1])
        row = spot[spot[code_col].astype(str).str.zfill(6) == data.code.zfill(6)]
        if not row.empty:
            r = row.iloc[0]
            data.nav        = _safe_float(r, ["最新价", "现价", "收盘价"])
            data.change_pct = _safe_float(r, ["涨跌幅"])
            # 溢折价：(现价 - 净值) / 净值 * 100
            nav_col = next((c for c in ["基金净值", "净值"] if c in row.columns), None)
            if nav_col:
                nav_val  = _safe_float(r, [nav_col])
                price_val = data.nav
                if nav_val and price_val and nav_val > 0:
                    data.premium_pct = (price_val - nav_val) / nav_val * 100
            # 规模
            data.aum_bn = _safe_float(r, ["总市值", "规模(亿)", "净资产(亿)"])
            if data.aum_bn and data.aum_bn > 1e4:
                data.aum_bn /= 1e8  # 转成亿

        # 费率 + 成立日期（较慢，设 timeout 保护）
        try:
            info = ak.fund_etf_fund_info_em(fund=data.code.zfill(6), page=1)
            if info is not None and not info.empty:
                _fill_fee_and_inception(data, info)
        except Exception:
            pass

    except Exception:
        pass


def _fetch_oef(data: FundData):
    """场外基金：fund_open_fund_info_em 获取规模/费率/净值。"""
    try:
        import akshare as ak

        # 净值
        try:
            nav_df = ak.fund_open_fund_info_em(fund=data.code, indicator="单位净值走势")
            if nav_df is not None and not nav_df.empty:
                last = nav_df.iloc[-1]
                nav_val = _safe_float(last, ["单位净值", "净值"])
                if nav_val:
                    data.nav = nav_val
                # 涨跌幅（当日）
                prev = nav_df.iloc[-2] if len(nav_df) > 1 else None
                if prev is not None:
                    pv = _safe_float(prev, ["单位净值", "净值"])
                    if pv and pv > 0 and nav_val:
                        data.change_pct = (nav_val - pv) / pv * 100
                # 成立时间
                try:
                    first_date = str(nav_df.iloc[0].get("净值日期", ""))
                    if first_date:
                        import datetime
                        d0 = datetime.datetime.strptime(first_date[:10], "%Y-%m-%d")
                        data.years_since_inception = (datetime.datetime.now() - d0).days / 365
                except Exception:
                    pass
        except Exception:
            pass

        # 规模
        try:
            size_df = ak.fund_open_fund_info_em(fund=data.code, indicator="基金规模")
            if size_df is not None and not size_df.empty:
                last_size = _safe_float(size_df.iloc[-1], ["规模", "基金规模(亿元)", "净资产(亿元)"])
                if last_size:
                    data.aum_bn = last_size
        except Exception:
            pass

        # 费率（从基本信息）
        try:
            meta_df = ak.fund_open_fund_info_em(fund=data.code, indicator="基本概况")
            if meta_df is not None and not meta_df.empty:
                _fill_fee_from_meta(data, meta_df)
        except Exception:
            pass

    except Exception:
        pass


# ── 辅助 ─────────────────────────────────────────────────

def _safe_float(row, cols):
    for c in cols:
        try:
            v = row[c]
            if v is not None and str(v).strip() not in ("", "—", "-", "N/A"):
                return float(str(v).replace("%", "").replace(",", ""))
        except Exception:
            continue
    return None


def _fill_fee_and_inception(data: FundData, df):
    """从 fund_etf_fund_info_em 结果填充费率和成立日期。"""
    for _, r in df.iterrows():
        key = str(r.get("item", r.get("指标", ""))).strip()
        val = str(r.get("value", r.get("值", ""))).strip()
        if "管理费" in key:
            m = __import__("re").search(r"[\d.]+", val)
            if m:
                data.fee_rate = float(m.group())
        if "成立日" in key or "设立日" in key:
            try:
                import datetime
                d0 = datetime.datetime.strptime(val[:10], "%Y-%m-%d")
                data.years_since_inception = (datetime.datetime.now() - d0).days / 365
            except Exception:
                pass


def _fill_fee_from_meta(data: FundData, df):
    for _, r in df.iterrows():
        key = str(r.iloc[0]).strip() if len(r) > 0 else ""
        val = str(r.iloc[1]).strip() if len(r) > 1 else ""
        if "管理费" in key:
            m = __import__("re").search(r"[\d.]+", val)
            if m:
                data.fee_rate = float(m.group())
        if "成立日" in key:
            try:
                import datetime
                d0 = datetime.datetime.strptime(val[:10], "%Y-%m-%d")
                data.years_since_inception = (datetime.datetime.now() - d0).days / 365
            except Exception:
                pass
