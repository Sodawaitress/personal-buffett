"""
Fetch analyst EPS consensus from 同花顺 for A-share stocks.
Data: institution count + EPS forecast (min/avg/max) for next 2 years.
Falls back gracefully if THS is blocked overseas.
"""
import time
from datetime import datetime, timezone


def fetch_analyst_consensus(code: str) -> dict | None:
    """
    Returns dict with:
      institution_count, forecasts (list of {year, eps_avg, eps_min, eps_max})
    or None if unavailable.
    """
    pure = code.split(".")[0]
    try:
        import akshare as ak
        df = ak.stock_profit_forecast_ths(symbol=pure, indicator='预测年报每股收益')
        if df is None or df.empty:
            return None
        forecasts = []
        for _, row in df.head(2).iterrows():
            try:
                forecasts.append({
                    "year":    str(int(row["年度"])),
                    "eps_avg": round(float(row["均值"]), 2),
                    "eps_min": round(float(row["最小值"]), 2),
                    "eps_max": round(float(row["最大值"]), 2),
                })
            except Exception:
                pass
        if not forecasts:
            return None
        count = int(df.iloc[0]["预测机构数"]) if not df.empty else 0
        return {
            "institution_count": count,
            "forecasts":         forecasts,
        }
    except Exception as e:
        print(f"    ⚠️ {code} analyst consensus: {e}")
        return None
