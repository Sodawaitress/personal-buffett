"""US-167：机构调研是「注意力」信号，不是「方向」信号。

## 用户提出的问题（2026-08-24）

> 这个机构接连两个月调研的红柱子，但是它的股价还是在跌，说明机构调研的时候
> 不一定马上就涨，值得关注，**或者说调研到最后并不值得机构买，也不一定**

她说对了系统做错的一件事。调研在两处被写死成单向看涨：

    _SIGNAL_DEFS["survey_visit"]  = {"direction": "bull", "weight": 2}
    意向分  dir_v = min(sv_score / 30.0, 1.0)     # 恒为正

**系统里没有任何路径能表达「机构去看了，然后决定不买」。**
调研次数越多分越高、越看涨 —— 而机构调研完全可以得出「不买」甚至「做空」的结论。

## 这是本仓第三次犯同一类错

| 信号 | 本质 | 曾被当成 |
|---|---|---|
| 北向 0.0 | 无数据 | 连续买入（US-151/155 已修）|
| 前兆分 `abs(融券变化)` | 活跃度 | 「机构在悄悄建仓」 |
| **机构调研** | **注意力** | **无条件看涨 bull/2** |

共同点：**无方向的量被贴上方向标签**。

## 本地 27 条样本的回测（样本小，只能当线索不能当结论）

    专项调研  11 条 · 中位数 +5.97% · 上涨 72%   ← 有信号
    其他调研  16 条 · 中位数 +0.57% · 上涨 50%   ← 抛硬币

所以「专项调研给看涨权重」是合理的，「其他调研给 bull/1」站不住。

## 做法

不猜方向，**查后续**：每次调研之后 N 个交易日股价怎么走了。
把这个「后续」显示在柱子旁边（用户想看的正是这个），并用它推导方向 ——
方向从数据里长出来，不是写死在表里。
"""

from datetime import date, timedelta

# 调研之后看多少个自然日的后续（约 14 个交易日）
FOLLOW_DAYS = 20

# 后续判定阈值：±3% 以内算「没动」。A 股日常波动大，阈值太小会把噪音判成方向。
_MOVE_THRESHOLD = 3.0

# 事件太新（后续窗口还没走完）不下结论，标成 pending
_MIN_ELAPSED = 7

# 至少要这么多个「已判定」事件才给方向。
# 2026-08-25 实测：只有 1 个已判定事件时，原逻辑会输出
# 「专项调研 1 次里 1 次之后反而跌了 —— 看完没买，甚至在卖」——
# n=1 下这种结论太重了，一次巧合就会被讲成规律。
_MIN_DECIDED = 2


def classify(pct):
    """后续涨跌 → 三态。None 表示还看不出来。"""
    if pct is None:
        return None
    if pct >= _MOVE_THRESHOLD:
        return "followed_up"      # 调研后涨了 → 机构大概率买了
    if pct <= -_MOVE_THRESHOLD:
        return "followed_down"    # 调研后跌了 → 看完没买，或看完在卖
    return "no_follow"            # 看完没动静


_LABEL = {
    "followed_up":   "调研后涨",
    "followed_down": "调研后跌",
    "no_follow":     "调研后没动",
    "pending":       "还太新，看不出",
}


def build(events: list, price_lookup, today: str = None) -> dict:
    """events = [{date, n_inst, is_specific, method}, ...]
    price_lookup(code_or_none, date_str) -> float | None，由调用方注入
    （这样单测不用碰 DB，生产里传一个查 stock_prices 的闭包）。

    返回 {
      "events": [{date, n_inst, is_specific, outcome, pct, label}, ...],
      "summary": {"up": n, "down": n, "flat": n, "pending": n},
      "direction": "bull" | "bear" | "neutral" | None,
      "confidence": "high" | "low" | None,
      "headline": "一句人话",
    }
    """
    today = today or date.today().isoformat()
    try:
        t = date.fromisoformat(today)
    except (ValueError, TypeError):
        return _empty()

    rows = []
    for e in events or []:
        d0 = str(e.get("date") or "")[:10]
        try:
            ed = date.fromisoformat(d0)
        except (ValueError, TypeError):
            continue
        elapsed = (t - ed).days
        if elapsed < 0:
            continue

        outcome, pct = "pending", None
        if elapsed >= _MIN_ELAPSED:
            p0 = price_lookup(d0)
            p1 = price_lookup((ed + timedelta(days=FOLLOW_DAYS)).isoformat())
            # 后续窗口还没走完时，用「今天」当终点，但标注是进行中
            if p0 and not p1 and elapsed < FOLLOW_DAYS:
                p1 = price_lookup(today)
            if p0 and p1 and p0 > 0:
                pct = round((p1 - p0) / p0 * 100, 1)
                outcome = classify(pct)

        rows.append({
            "date": d0,
            "n_inst": int(e.get("n_inst") or 0),
            "is_specific": bool(e.get("is_specific")),
            "method": e.get("method") or "",
            "outcome": outcome,
            "pct": pct,
            "label": _LABEL.get(outcome, ""),
        })

    if not rows:
        return _empty()

    rows.sort(key=lambda r: r["date"], reverse=True)
    summary = {
        "up":      sum(1 for r in rows if r["outcome"] == "followed_up"),
        "down":    sum(1 for r in rows if r["outcome"] == "followed_down"),
        "flat":    sum(1 for r in rows if r["outcome"] == "no_follow"),
        "pending": sum(1 for r in rows if r["outcome"] == "pending"),
    }
    direction, confidence, headline = _judge(rows, summary)
    return {"events": rows, "summary": summary, "direction": direction,
            "confidence": confidence, "headline": headline}


def _empty():
    return {"events": [], "summary": {"up": 0, "down": 0, "flat": 0, "pending": 0},
            "direction": None, "confidence": None, "headline": ""}


def _judge(rows, summary):
    """方向从后续里推导，不是写死的。

    **专项调研权重更高**：本地回测里专项调研上涨 72%、其他调研 50%（抛硬币），
    所以只有专项调研的后续才配影响方向；普通调研只计入「有人在看」。
    """
    decided = [r for r in rows if r["outcome"] and r["outcome"] != "pending"]
    if not decided:
        return None, None, "调研后的走势还看不出来（事件太新，或缺少当时的价格数据）"
    specific = [r for r in decided if r["is_specific"]]
    basis = specific or decided

    # 样本量检查必须看 basis，不能看 decided ——
    # 方向是 basis 算出来的，拿 decided 的条数去放行，等于用 3 条普通调研
    # 给 1 条专项调研的结论背书。（2026-08-25 被 test_specific_surveys_take_precedence 抓到）
    if len(basis) < _MIN_DECIDED:
        one = basis[0]
        return None, None, (
            f"只有 1 次调研的后续可查（{one['date']} 之后 {one['pct']:+.1f}%），"
            f"样本太少，不足以说明调研有没有变成买入")

    up = sum(1 for r in basis if r["outcome"] == "followed_up")
    down = sum(1 for r in basis if r["outcome"] == "followed_down")
    n = len(basis)
    kind = "专项调研" if specific else "调研"

    if up > down and up * 2 >= n:
        d, head = "bull", f"{kind} {n} 次里 {up} 次之后涨了 —— 机构看完是买了"
    elif down > up and down * 2 >= n:
        d, head = "bear", f"{kind} {n} 次里 {down} 次之后反而跌了 —— **看完没买，甚至在卖**"
    else:
        d, head = "neutral", f"{kind} {n} 次，之后涨跌各半 —— 调研本身没预示方向"

    # 只有专项调研 + 样本 ≥3 才算高置信；否则明说信心低
    conf = "high" if (specific and n >= 3) else "low"
    if conf == "low":
        head += "（样本少，仅供参考）"
    return d, conf, head


def db_price_lookup(code: str):
    """返回一个 price_lookup(date) 函数，从 stock_prices 读收盘价。

    build() 本身不碰数据库（价格查询由调用方注入），方便测试。
    这个工厂是**唯一**的真实实现 —— presenter 和 signal_events 都用它，
    免得两处各写一份、慢慢长歪。
    """
    from radar_app.data.core import get_conn

    def _price_at(d: str):
        """取 d 当天或之后最近的收盘价（往后找 6 天，跨周末/长假）。"""
        try:
            from datetime import date as _d, timedelta as _td
            end = (_d.fromisoformat(str(d)[:10]) + _td(days=6)).isoformat()
        except (ValueError, TypeError):
            return None
        with get_conn() as c:
            row = c.execute(
                "SELECT price FROM stock_prices WHERE code=:c "
                "AND fetched_at >= :a AND fetched_at <= :b "
                "ORDER BY fetched_at ASC LIMIT 1",
                {"c": code, "a": str(d)[:10], "b": end + " 23:59:59"},
            ).fetchone()
        return row["price"] if row and row["price"] else None

    return _price_at
