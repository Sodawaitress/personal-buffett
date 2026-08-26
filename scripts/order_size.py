"""订单有多大 —— 不比谁先看到，比谁先看懂（US-183）。

## 用户妈妈的问题（2026-08-26）

> 「我们得不到最新的消息……有一个就是看他的订单量，这个是不是可以？
>  他得到了订单量过后的反应，是不是也是极快地在股价上面表现呢」

她的方向是对的，但「快」不是可以争的东西：

**中标/重大合同是强制披露的，公告一出来所有人同时看到。** 拼速度，
散户永远输给盯盘的机构和程序。签约到公告还有几天延迟，这几天也补不上。

**但有一件事是可以赢的：拼「谁先看懂」。**

公告写「中标 1.2 亿元」，绝大多数人不会当场去算：
**这占这家公司一年营收的百分之几？**

    营收 10 亿的公司  → 1.2 亿 = 12% 的年营收，**是大事**
    营收 1000 亿的公司 → 1.2 亿 = 0.12%，**是噪音**

同一个数字，意义能差一百倍。而这个换算我们做得起 —— 营收在
stock_fundamentals 的年报里，公告金额在标题里。

## 为什么这属于「公司本身」那一层

按 US-179 的五层链，订单是**真实的经营变化**，属于最上面那层，
不是「市场的钱」那种噪音。它的价值不在于领先几天，在于它**是真的**。

## 局限（必须写出来）

- 金额**只在标题带数字时**才抓得到。很多公告写「签订日常经营重大合同」，
  金额在正文里 —— 抓不到就返回 None，**不猜**。
- 「中标」不等于「已确认收入」：可能分几年执行，可能被取消。
- 年营收用最近一个完整财年，本身滞后 —— 但用来做量级换算够了，
  这里要的是「百分之几」不是精确值。
"""
import re

# 中文金额单位。注意「万」和「亿」的量级差 10000 倍，弄反就是灾难性误读。
_UNITS = {"亿": 1e8, "万": 1e4, "千万": 1e7, "百万": 1e6}

# 「约 1.2 亿元」「金额 12,345.67 万元」「人民币 3.5 亿」
_AMOUNT_RE = re.compile(
    r"(?:约|计|达|金额|合计|总额|价款|中标价)?\s*"
    r"(?:人民币|RMB)?\s*"
    r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*"
    r"(亿|千万|百万|万)\s*(?:元|人民币)?"
)


def extract_amount(text: str):
    """从公告标题里抠出金额（元）。抠不到返回 None —— **不猜**。

    取**最大**的那个数：标题里可能同时出现「中标金额 1.2 亿元，
    占公司最近一期经审计营业收入的 3.5%」这种，后面那个 3.5 不是金额。
    但百分数不带单位，不会被这个正则命中，所以取最大是安全的。
    """
    if not text:
        return None
    best = None
    for m in _AMOUNT_RE.finditer(str(text)):
        try:
            num = float(m.group(1).replace(",", ""))
        except (TypeError, ValueError):
            continue
        val = num * _UNITS.get(m.group(2), 0)
        if val <= 0:
            continue
        if best is None or val > best:
            best = val
    return best


def latest_revenue(annual: list):
    """最近一个完整财年的营收（元）。年报里存的单位是「亿」。"""
    for y in annual or []:
        try:
            rev = float(y.get("revenue"))
        except (TypeError, ValueError):
            continue
        if rev and rev > 0:
            return rev * 1e8
    return None


# 占年营收多少算「值得看」。低于这个数，一单再大也只是日常经营。
_MATERIAL_PCT = 5.0
_BIG_PCT = 20.0


def size_up(title: str, annual: list, locale: str = "zh") -> dict:
    """把一条订单公告换算成「占年营收百分之几」，并给一句人话。

    返回 {} 表示算不出来（标题没金额、或没有营收数据）—— **不编**。
    """
    amt = extract_amount(title)
    rev = latest_revenue(annual)
    if not amt or not rev:
        return {}
    pct = round(amt / rev * 100, 1)
    if pct >= _BIG_PCT:
        tier, word = "big", "相当大的一单"
    elif pct >= _MATERIAL_PCT:
        tier, word = "material", "值得注意"
    else:
        tier, word = "routine", "占比不大，接近日常经营"
    if locale == "en":
        text = (f"About {_fmt_en(amt)}, roughly {pct}% of last full year's revenue"
                f" — {'a large order' if tier == 'big' else 'worth noting' if tier == 'material' else 'small relative to the business'}")
    else:
        text = f"约 {_fmt_cn(amt)}，相当于上一个完整财年营收的 {pct}% —— {word}"
    return {"amount": amt, "revenue": rev, "pct": pct, "tier": tier, "text": text}


def _fmt_cn(v):
    if v >= 1e8:
        return f"{v / 1e8:.2f} 亿元"
    return f"{v / 1e4:.0f} 万元"


def _fmt_en(v):
    return f"RMB {v / 1e8:.2f}00 million" if v >= 1e8 else f"RMB {v / 1e4:.0f}0k"
