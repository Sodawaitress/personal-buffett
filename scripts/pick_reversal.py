"""US-166：已推荐股票的信号反转检测。

## 为什么要有它（真实事故，2026-08-19 → 08-22）

8/19 的五选把小商品城(600415) 写成「本轮 5 只中最干净的信号组合」，依据是
**融券余量大减 56.2%（空头退场）**，操作提示「未持仓可小仓位建仓 ¥12.30 附近」。

三天后（8/22）同一只股票的融券变成 **+118.1%** —— 空头不但回来了，规模还翻倍。
**中间没有任何一封信提醒过。** 用户妈妈按 8/19 的建议加仓，当天就被套。

根因不是数据错，是**五选是「选股」而不是「持仓管理」**：推荐完就断了。
Run 2 只验证显式写下的 1–2 条「预言」，不管 5 只各自的「操作提示」。

## 为什么检测逻辑必须在代码里

放在 CLAUDE_ROUTINE.md 的提示词里 = 靠 Claude 每天记得回头查。
这个仓库所有的沉默失败都证明了「靠自觉」不成立。所以：
digest-svc 每天算好反转清单塞进快照，Routine 只能读、没法忘。

## 为什么按「推荐过」而不是「持仓」

用户妈妈买了小商品城，但系统里它的 status 仍是 `watching`、`entry_price` 为
null —— 在券商下单不会回流到这里。**所以基于持仓的回访对她根本不生效。**
判据必须是「系统说过什么」，那份数据我们有（Routine 写的 picks 台账）。
"""

import json
from datetime import date, datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))

# 推荐后跟踪多少天。超过就自然关闭 —— 再久的反转已经和当初那次推荐无关了。
TRACK_DAYS = 21

# 融券反转的判定：不是看绝对值，是看**方向翻转**。
# 从「空头退场」变成「空头回来」，或反过来，才叫反转。
# 阈值 30 与 fetch_short_selling_trend 的 trend 分档一致（±30% 才算有方向）。
_SHORT_DIR_THRESHOLD = 30.0


def _short_dir(change_pct):
    """把融券变化折成三态。None / 基数无效 → None（不参与反转判断）。"""
    if change_pct is None:
        return None
    if change_pct >= _SHORT_DIR_THRESHOLD:
        return "building"        # 空头在建仓
    if change_pct <= -_SHORT_DIR_THRESHOLD:
        return "retreating"      # 空头在撤
    return "flat"


_GRADE_RANK = {"A+": 0, "A": 1, "B+": 2, "B": 3, "B-": 4,
               "C+": 5, "C": 6, "D": 7, "NR": 9}


def _grade_drop(before, after):
    """评级掉了几档。升级返回负数。未知评级返回 None。"""
    a, b = _GRADE_RANK.get(before), _GRADE_RANK.get(after)
    if a is None or b is None:
        return None
    return b - a


def detect_reversals(picks: list, snapshot_stocks: list, today: str = None) -> list:
    """picks = Routine 写的台账；snapshot_stocks = 今天快照里的 stocks。

    返回 [{code, name, picked_date, days_since, reasons[], before{}, after{}}, ...]
    只返回**真的反转了**的，没反转的不占篇幅。
    """
    today = today or datetime.now(CN_TZ).strftime("%Y-%m-%d")
    by_code = {s.get("code"): s for s in (snapshot_stocks or [])}
    out = []

    for p in picks or []:
        code = p.get("code")
        picked = str(p.get("date") or "")[:10]
        if not code or not picked:
            continue
        try:
            d0 = date.fromisoformat(picked)
            d1 = date.fromisoformat(today)
        except ValueError:
            continue
        days = (d1 - d0).days
        if days < 1 or days > TRACK_DAYS:
            continue                      # 当天不算；超过跟踪窗口自然关闭

        cur = by_code.get(code)
        if not cur:
            continue

        pre = p.get("signals") or {}
        ana = cur.get("analysis") or {}
        pc = cur.get("precursor") or {}
        sh = pc.get("short_selling") or {}

        reasons = []

        # ① 融券方向翻转 —— 小商品城就是这一条
        d_before = _short_dir(pre.get("short_change_pct"))
        d_after = _short_dir(sh.get("change_pct"))
        # 基数无效时不判（US-163：分母噪音不是信号）
        if sh.get("meaningful") is False:
            d_after = None
        if d_before and d_after and d_before != d_after and "flat" not in (d_before, d_after):
            word = {"building": "空头在建仓", "retreating": "空头在撤"}
            reasons.append(
                f"融券方向翻转：{word[d_before]}（{pre.get('short_change_pct'):+.0f}%）"
                f" → {word[d_after]}（{sh.get('change_pct'):+.0f}%）")

        # ② 评级下调 ≥1 档
        drop = _grade_drop(pre.get("grade"), ana.get("grade"))
        if drop is not None and drop >= 1:
            reasons.append(f"评级下调：{pre.get('grade')} → {ana.get('grade')}")

        # ③ 结论转向卖出侧
        _SELL = ("减持", "卖出", "回避", "坚决回避")
        if ana.get("conclusion") in _SELL and pre.get("conclusion") not in _SELL:
            reasons.append(f"结论转向：{pre.get('conclusion')} → {ana.get('conclusion')}")

        # ④ 当初的依据是「有机构调研」，现在调研归零
        sv_before = pre.get("survey_count_30d")
        sv_after = (pc.get("survey") or {}).get("count_30d")
        if (sv_before or 0) > 0 and sv_after == 0:
            reasons.append(f"机构调研归零：30 日 {sv_before} 次 → 0 次")

        if reasons:
            out.append({
                "code": code,
                "name": cur.get("name") or p.get("name") or code,
                "picked_date": picked,
                "days_since": days,
                "picked_advice": (p.get("advice") or "")[:120],
                "reasons": reasons,
                "price_then": pre.get("price"),
                "price_now": (cur.get("price") or {}).get("current"),
            })

    out.sort(key=lambda x: -len(x["reasons"]))
    return out


def signals_of(stock: dict) -> dict:
    """从快照条目抽出「当时的关键信号」，供 Routine 写台账时直接用。

    只存反转判断需要的那几个字段 —— 台账不是快照副本，存多了会腐烂。
    """
    ana = stock.get("analysis") or {}
    pc = stock.get("precursor") or {}
    sh = pc.get("short_selling") or {}
    return {
        "grade": ana.get("grade"),
        "conclusion": ana.get("conclusion"),
        "quant_score": ana.get("quant_score"),
        "short_change_pct": sh.get("change_pct"),
        "survey_count_30d": (pc.get("survey") or {}).get("count_30d"),
        "price": (stock.get("price") or {}).get("current"),
    }
