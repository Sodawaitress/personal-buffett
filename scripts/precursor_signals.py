"""
precursor_signals.py — 机构前兆信号层（比可见行为早 1-4 周）

三类信号：
  1. 机构调研热度  — stock_jgdy_tj_em，前兆性最强，中国特有
  2. 融券余量趋势  — stock_margin_detail_sse/szse，聪明做空信号
  3. 机构参与度趋势 — stock_comment_detail_zlkp_jgcyd_em，日频
"""

import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from scripts.config import CN_TZ


def _safe_float(val, default=0.0):
    try:
        f = float(val)
        return f if f == f else default  # NaN check
    except (TypeError, ValueError):
        return default


def _cn_codes():
    try:
        import db
        return [code for code, _ in db.get_active_watchlist_stocks()]
    except Exception:
        return []


# ── 接待方式权重 ─────────────────────────────────────────────────────
# 特定对象调研/现场参观 = 机构专程预约，最有含义
# 分析师会议/路演 = 有选择性
# 业绩说明会/电话会议（全员参加型）= 例行，含金量低
_MEETING_WEIGHTS = {
    "特定对象调研": 2.5,
    "现场参观":     2.0,
    "分析师会议":   1.8,
    "路演活动":     1.5,
    "电话接待":     1.0,
    "电话会议":     0.8,
    "电话交流":     0.8,
    "业绩说明会":   0.3,
    "业绩交流会":   0.3,
    "线上文字问答": 0.2,
    "网络文字互动": 0.2,
}
_DEFAULT_MEETING_WEIGHT = 0.5


def _meeting_weight(method_str: str) -> float:
    """按接待方式字符串计算权重，取最高值。"""
    best = _DEFAULT_MEETING_WEIGHT
    for keyword, w in _MEETING_WEIGHTS.items():
        if keyword in (method_str or ""):
            best = max(best, w)
    return best


def _recency_factor(survey_date_str: str, today: datetime) -> float:
    """越近权重越高：7日内=1.0，30日内=0.5，60日内=0.25。"""
    try:
        d = datetime.strptime(str(survey_date_str)[:10], "%Y-%m-%d").replace(
            tzinfo=today.tzinfo
        )
        days_ago = (today - d).days
        if days_ago <= 7:
            return 1.0
        if days_ago <= 30:
            return 0.5
        if days_ago <= 60:
            return 0.25
    except Exception:
        pass
    return 0.0


# ── 1. 机构调研热度 ──────────────────────────────────────────────────

def _fetch_jgdy_tj() -> pd.DataFrame | None:
    """
    拉机构调研统计。date 参数是"公告日期大于该日"的过滤条件，
    传年初日期可获取近一年数据（含接待日期字段供二次筛选）。
    """
    today = datetime.now(CN_TZ)
    year_start = f"{today.year}0101"
    try:
        df = ak.stock_jgdy_tj_em(date=year_start)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"  ⚠️ 机构调研接口失败: {e}")
    return None


def fetch_survey_activity(codes: set = None) -> dict:
    """
    返回 {code: {"score": float, "desc": str, "events": [...]}}
    score 含义：0=无调研, 10+=机构密集专项调研
    """
    if codes is None:
        codes = set(_cn_codes())
    if not codes:
        return {}

    today = datetime.now(CN_TZ)
    cutoff_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")

    result = {}
    try:
        df = _fetch_jgdy_tj()
        if df is None or df.empty:
            return {}

        # 只看 60 天内的调研记录
        df["接待日期"] = pd.to_datetime(df["接待日期"], errors="coerce")
        df = df[df["接待日期"] >= cutoff_date]

        # 只保留自选股（标准化为 6 位字符串再比对，防止 2460 ≠ 002460）
        df["_code6"] = df["代码"].astype(str).str.zfill(6)
        codes6 = {str(c).zfill(6) for c in codes}
        hits = df[df["_code6"].isin(codes6)].copy()
        if hits.empty:
            return {}

        # 去重（同一次调研在不同查询日期重复出现）
        hits = hits.drop_duplicates(subset=["_code6", "接待日期", "接待方式"])

        for code6, group in hits.groupby("_code6"):
            code = code6  # normalized
            events = []
            total_score = 0.0

            for _, row in group.iterrows():
                n_inst = _safe_float(row.get("接待机构数量", 1))
                method = str(row.get("接待方式", ""))
                survey_date = str(row.get("接待日期", ""))
                name = str(row.get("名称", code))

                m_w = _meeting_weight(method)
                r_f = _recency_factor(survey_date, today)
                event_score = n_inst * m_w * r_f

                # 统一格式化为 YYYY-MM-DD 字符串
                date_str = (survey_date.strftime("%Y-%m-%d")
                            if hasattr(survey_date, "strftime")
                            else str(survey_date)[:10])
                events.append({
                    "date":    date_str,
                    "method":  method,
                    "n_inst":  int(n_inst),
                    "score":   round(event_score, 1),
                    "is_specific": "特定对象调研" in method or "现场参观" in method,
                })
                total_score += event_score

            # 生成人话描述
            specific = [e for e in events if e["is_specific"]]
            if specific:
                latest = max(specific, key=lambda x: x["date"])
                desc = (
                    f"{latest['n_inst']}家机构专程{latest['date']}来调研"
                    f"（{latest['method'].split(',')[0]}）"
                    f"——机构花时间来看，说明有明确兴趣"
                )
            elif events:
                best = max(events, key=lambda x: x["n_inst"])
                desc = (
                    f"{best['n_inst']}家机构参加{best['date']}的{best['method'].split(',')[0]}"
                )
            else:
                desc = "近期无机构调研记录"

            result[code] = {
                "score":    round(total_score, 1),
                "desc":     desc,
                "events":   sorted(events, key=lambda x: x["date"], reverse=True),
                "name":     name,
            }

    except Exception as e:
        print(f"  ⚠️ 机构调研拉取失败: {e}")

    return result


# ── 2. 融券余量趋势（聪明钱做空信号） ────────────────────────────────

def _find_margin_row(code: str, is_sse: bool, lookback_start: int, lookback_end: int) -> dict | None:
    """在 lookback_start..lookback_end 天前范围内找最近有效融券数据。"""
    today = datetime.now(CN_TZ)
    col_code  = "标的证券代码" if is_sse else "证券代码"
    col_short = "融券余量"

    for delta in range(lookback_start, lookback_end + 1):
        d = (today - timedelta(days=delta)).strftime("%Y%m%d")
        try:
            df = (ak.stock_margin_detail_sse(date=d) if is_sse
                  else ak.stock_margin_detail_szse(date=d))
            if df is None or df.empty:
                continue
            row = df[df[col_code].astype(str).str.zfill(6) == code.zfill(6)]
            if not row.empty:
                return {"date": d, "short_mn": _safe_float(row.iloc[0].get(col_short, 0)) / 1e4}
        except Exception:
            pass
        time.sleep(0.2)
    return None


def fetch_short_selling_trend(code: str, days: int = 30) -> dict:
    """
    返回 {
        "latest_short": float,    # 最新融券余量（万股）
        "change_pct": float,      # 相比30日前变化%
        "trend": str,             # "做空增加"|"做空减少"|"中性"
        "desc": str,
        "valid": bool,
    }
    """
    is_sse = code.startswith(("6", "9"))

    # 取两个数据点：最近 3 天内 和 30 天前附近各取一个
    latest_row  = _find_margin_row(code, is_sse, 1, 5)
    earlier_row = _find_margin_row(code, is_sse, days - 3, days + 3)
    rows = [r for r in [earlier_row, latest_row] if r]

    if len(rows) < 2:
        return {"valid": False, "desc": "融券数据不足"}

    rows.sort(key=lambda x: x["date"])
    latest = rows[-1]["short_mn"]
    earliest = rows[0]["short_mn"]

    if earliest <= 0:
        return {"valid": False, "desc": "融券基准数据为零"}

    change_pct = round((latest - earliest) / earliest * 100, 1)

    if change_pct >= 30:
        trend = "做空增加"
        desc = f"融券余量近30日增加{change_pct:.0f}%（{earliest:.1f}万→{latest:.1f}万股）——聪明钱在做空，对后市谨慎"
    elif change_pct <= -30:
        trend = "做空减少"
        desc = f"融券余量近30日减少{abs(change_pct):.0f}%（{earliest:.1f}万→{latest:.1f}万股）——空头在平仓，可能是底部信号"
    else:
        trend = "中性"
        desc = f"融券余量基本稳定（{change_pct:+.0f}%，当前{latest:.1f}万股）"

    return {
        "latest_short": round(latest, 1),
        "change_pct":   change_pct,
        "trend":        trend,
        "desc":         desc,
        "valid":        True,
        "history":      rows,
    }


# ── 3. 机构参与度趋势 ────────────────────────────────────────────────

def fetch_inst_participation_trend(code: str) -> dict:
    """
    返回近期机构参与度均值和最新值，检测异常高位。
    {
        "latest": float,
        "avg_30d": float,
        "spike": bool,     # 最新值 > avg + 1.5σ
        "trend": str,      # "上升"|"下降"|"中性"
        "desc": str,
        "valid": bool,
    }
    """
    try:
        df = ak.stock_comment_detail_zlkp_jgcyd_em(symbol=code)
        if df is None or df.empty:
            return {"valid": False, "desc": "无机构参与度数据"}

        # 列名在不同 AKShare 版本可能不同，动态识别
        date_col = next((c for c in df.columns
                         if any(k in c for k in ["交易日", "日期", "date", "Date"])), None)
        part_col = next((c for c in df.columns
                         if any(k in c for k in ["参与度", "机构参与", "参与比"])), None)
        if not date_col or not part_col:
            return {"valid": False, "desc": f"数据格式变化，无法解析（列：{list(df.columns)[:5]}）"}

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values(date_col).tail(30)

        vals = df[part_col].apply(lambda x: _safe_float(x, None)).dropna().tolist()
        if len(vals) < 5:
            return {"valid": False, "desc": "数据不足"}

        import statistics
        latest = vals[-1]
        avg    = statistics.mean(vals)
        stdev  = statistics.stdev(vals) if len(vals) > 1 else 1.0

        spike  = latest > avg + 1.5 * stdev
        recent_5  = statistics.mean(vals[-5:])
        prev_5    = statistics.mean(vals[-10:-5]) if len(vals) >= 10 else avg

        if recent_5 > prev_5 + 2:
            trend = "上升"
        elif recent_5 < prev_5 - 2:
            trend = "下降"
        else:
            trend = "中性"

        # 用5日窗口值生成描述，避免均值和趋势方向矛盾
        if spike:
            desc = (
                f"今天机构交易异常活跃（参与度{latest:.0f}，"
                f"比近30天均值{avg:.0f}高出{latest - avg:.0f}）"
                f"——机构在大动作，但方向不明"
            )
        elif trend == "上升":
            desc = (
                f"近5天机构参与度在上升（从{prev_5:.0f}升至{recent_5:.0f}）"
                f"——机构越来越关注这只股票"
            )
        elif trend == "下降":
            desc = (
                f"近5天机构参与度在下降（从{prev_5:.0f}降至{recent_5:.0f}）"
                f"——机构在减少操作，关注度下滑"
            )
        else:
            desc = f"机构参与度平稳（当前{latest:.0f}，近期均值{avg:.0f}），没有异常波动"

        return {
            "latest":    round(latest, 1),
            "avg_30d":   round(avg, 1),
            "stdev":     round(stdev, 1),
            "recent_5":  round(recent_5, 1),
            "prev_5":    round(prev_5, 1),
            "spike":     spike,
            "trend":     trend,
            "desc":      desc,
            "valid":     True,
        }
    except Exception as e:
        return {"valid": False, "desc": f"数据拉取失败: {e}"}


# ── 主入口：整合三个信号 ─────────────────────────────────────────────

def fetch_precursor_signals(codes: list = None) -> dict:
    """
    对每只 A 股代码返回前兆信号汇总。
    返回 {code: {"survey": ..., "short": ..., "participation": ..., "summary": str}}
    """
    if codes is None:
        codes = _cn_codes()
    codes = [c for c in codes if c and len(c) == 6 and c.isdigit()]
    if not codes:
        return {}

    print("  🔍 前兆信号：机构调研活动…")
    surveys = fetch_survey_activity(set(codes))

    result = {}
    for i, code in enumerate(codes):
        if i > 0 and i % 5 == 0:
            time.sleep(1)  # 避免 API 限速

        sv = surveys.get(code, {"score": 0, "desc": "近期无机构调研", "events": []})

        print(f"  🔍 前兆信号 [{i+1}/{len(codes)}] {code}：融券趋势…")
        short = fetch_short_selling_trend(code)

        print(f"  🔍 前兆信号 [{i+1}/{len(codes)}] {code}：机构参与度…")
        part = fetch_inst_participation_trend(code)

        # 生成一句话摘要：取最显著的信号
        signals = []
        if sv["score"] >= 5:
            signals.append(f"调研热度高（{sv['desc']}）")
        if short.get("valid") and short["trend"] == "做空增加":
            signals.append(short["desc"][:30] + "…")
        if part.get("valid") and part["spike"]:
            signals.append(part["desc"][:30] + "…")

        summary = "；".join(signals) if signals else "暂无显著前兆信号"

        result[code] = {
            "survey":        sv,
            "short_selling": short,
            "participation": part,
            "summary":       summary,
        }

    return result
