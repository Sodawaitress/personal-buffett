"""
Industry signal fetcher for US-95.
Maps company_type → industry key → AKShare board index data.
Returns structured dict; never raises — always returns {} on failure.
"""

from datetime import datetime, timedelta, timezone

# Map company_type → (industry_key, display_label, em_board_name)
_INDUSTRY_MAP = {
    "cycle_commodity": ("cn_cycle_commodity", "工程机械/周期板块", "专用机械"),
    "growth_tech":     ("cn_growth_tech",     "半导体/科技板块",   "半导体"),
    "bank_insurance":  ("cn_bank_insurance",  "银行板块",          "银行"),
}

# Fallback board names to try if primary fails
_BOARD_FALLBACKS = {
    "专用机械": ["工程机械", "机械设备", "通用机械"],
    "半导体":   ["电子元器件", "消费电子", "光伏设备"],
    "银行":     ["证券", "保险"],
}

_CACHE_HOURS = 24


def get_industry_key(company_type: str) -> str | None:
    entry = _INDUSTRY_MAP.get(company_type)
    return entry[0] if entry else None


def fetch_industry_signal(company_type: str) -> dict:
    """Fetch or compute industry signal for the given company_type.

    Returns a dict with keys: industry_key, label, change_30d, signal, description, fetched_at
    Returns {} if company_type not mapped or on any error.
    """
    entry = _INDUSTRY_MAP.get(company_type)
    if not entry:
        return {}
    industry_key, label, board_name = entry

    # Try primary board name, then fallbacks
    names_to_try = [board_name] + _BOARD_FALLBACKS.get(board_name, [])
    for name in names_to_try:
        result = _fetch_board_30d(name)
        if result is not None:
            change_30d = result
            return _build_signal_dict(industry_key, label, change_30d, name)

    return {}


def _fetch_board_30d(board_name: str) -> float | None:
    """Return 30-day price change % for the named EM industry board, or None on failure."""
    try:
        import akshare as ak
        end_date   = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=35)).strftime("%Y%m%d")
        df = ak.stock_board_industry_hist_em(
            symbol=board_name,
            start_date=start_date,
            end_date=end_date,
            period="日k",
            adjust="",
        )
        if df is None or df.empty:
            return None
        # Expect columns: 日期, 开盘, 收盘, 最高, 最低, ...
        close_col = next((c for c in df.columns if "收盘" in c), None)
        if not close_col:
            return None
        df = df.sort_values("日期").reset_index(drop=True)
        first_close = float(df[close_col].iloc[0])
        last_close  = float(df[close_col].iloc[-1])
        if first_close <= 0:
            return None
        return round((last_close / first_close - 1) * 100, 2)
    except Exception:
        return None


def _build_signal_dict(industry_key: str, label: str, change_30d: float, board_name: str) -> dict:
    if change_30d >= 5:
        signal = "顺风"
        description = f"{label}近30日上涨 {change_30d:+.1f}%，板块处于上行态势"
    elif change_30d <= -5:
        signal = "逆风"
        description = f"{label}近30日下跌 {change_30d:+.1f}%，行业面临调整压力"
    else:
        signal = "中性"
        description = f"{label}近30日涨跌 {change_30d:+.1f}%，板块震荡整理"

    return {
        "industry_key": industry_key,
        "label":        label,
        "board_name":   board_name,
        "change_30d":   change_30d,
        "signal":       signal,
        "description":  description,
        "fetched_at":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_cycle_commodity_signal() -> dict:
    """Specialized fetch for cycle_commodity: try construction PMI as supplemental context."""
    base = fetch_industry_signal("cycle_commodity")
    if not base:
        return {}
    # Attempt to enrich with consecutive positive/negative months from manufacturing PMI
    consecutive = _calc_pmi_streak()
    if consecutive is not None:
        base["consecutive_months"] = consecutive
        if consecutive >= 3:
            base["cycle_tag"] = "上行周期确认"
        elif consecutive <= -2:
            base["cycle_tag"] = "下行压力"
        else:
            base["cycle_tag"] = ""
    return base


def _calc_pmi_streak() -> int | None:
    """Return consecutive positive PMI months (positive = expansion >50).
    Returns negative count for contraction streak, None on failure."""
    try:
        import akshare as ak
        df = ak.macro_china_pmi_yearly()
        if df is None or df.empty:
            return None
        # Columns may vary; look for 制造业PMI or similar
        pmi_col = next((c for c in df.columns if "制造业" in c or "PMI" in c.upper()), None)
        if not pmi_col:
            return None
        vals = df[pmi_col].dropna().astype(float).tolist()
        vals = vals[-6:]  # last 6 months
        if not vals:
            return None
        streak = 0
        direction = 1 if vals[-1] >= 50 else -1
        for v in reversed(vals):
            if direction == 1 and v >= 50:
                streak += 1
            elif direction == -1 and v < 50:
                streak -= 1
            else:
                break
        return streak
    except Exception:
        return None
