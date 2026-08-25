"""信息传导链：页面的骨架（US-179）。

## 这条链原本只是一句说明文字

`i18n/stock.json` 里早就写着：

    研究 → 参与 → 资金 → 价格：调研和机构参与度动得最早，是最前面的领先信号

**这句话是对的。但我们只把它当说明，没把它当骨架。** 于是同一张卡上并排
摆着「以天计」和「以季计」的东西，用同一种红绿、同一种百分比 ——
用户妈妈接连问出的五个问题，全都是这个结构的必然产物：

    「华测检测是 A 级，为什么是看空预警？」   ← 比的是不同层
    「机构接连调研，股价却在跌」               ← 调研在第 2 层且无方向
    「都长成这样了，他说股价还没反应」         ← 第 5 层早就走完了
    「这个内部人士买入是 4 月，太滞后了」      ← 第 1 层，半衰期约 1 个月
    「一个 C+ 说看多，一个 A 说看空」          ← 两个系统的输出并排放

## 为什么用「谁在说」当主轴

摊开全部信号后发现，三个维度在这一个轴上高度对齐：

    谁在说        独立于价格   兑现快慢   可信度
    公司自己人      是          月内       最高
    专业机构        是          季         高
    市场资金        半          天-周      中
    价格自己        否          —          背景

**越靠近公司的人，知道得越早、越独立于价格、越可信；
越靠近价格的信号，反应越快，但它只是在复述已经发生的事。**

均线、VWAP 在结构上**不可能领先价格** —— 它们就是价格的另一种写法
（文献称内部人信号 "exogenous to price action"，而均线是 endogenous）。

而「谁在说」对非专业读者也最直观：不需要理解半衰期，只要理解「谁离公司更近」。

## 半衰期

一条信号的有用程度会随时间衰减，掉到一半所需的时间就是半衰期。
内部人买入约 1 个月（Wharton 全样本：约 1/4 的超额收益在头 5 天、
约 1/2 在头 1 个月兑现）；主力资金约几天；均线没有半衰期，因为它本不领先。
"""

# 层的顺序**就是**信息传导的顺序。改顺序等于改模型，不要随手动。
LAYERS = [
    {
        "key": "company",
        "order": 0,
        "name": "这家公司本身怎么样",
        "short": "公司本身",
        "hint": "护城河、赚不赚钱、贵还是便宜 —— 这是底子，不是信号",
        "scale": "以年看",
        "half_life": None,          # 不是信号，无衰减
        "directional": True,
    },
    {
        "key": "insider",
        "order": 1,
        "name": "公司里的人在买还是在卖",
        "short": "自己人",
        "hint": "他们最了解自己公司。但等你看到公告，往往已经过去几周",
        "scale": "以月看",
        "half_life": "约 1 个月",
        "directional": True,
    },
    {
        "key": "institution",
        "order": 2,
        "name": "上门研究它的机构在做什么",
        "short": "机构",
        "hint": "去看过、买过、给过评级。调研只说明「有人在看」，不说明看多看空",
        "scale": "以季看",
        "half_life": "约 1 个季度",
        "directional": False,       # 调研本身无方向（US-167）
    },
    {
        "key": "money",
        "order": 3,
        "name": "市场上的钱往哪走",
        "short": "市场的钱",
        "hint": "今天谁在买谁在卖。反应最快，也最容易是噪音",
        "scale": "以天看",
        "half_life": "几天",
        "directional": True,
    },
    {
        "key": "price",
        "order": 4,
        "name": "价格自己走成什么样",
        "short": "价格本身",
        "hint": "均线、成交量这些是**价格算出来的**，它们不领先价格，只是复述",
        "scale": "看背景",
        "half_life": None,          # 派生量，谈不上领先
        "directional": False,
    },
]

_BY_KEY = {L["key"]: L for L in LAYERS}
LAYER_ORDER = [L["key"] for L in LAYERS]


# 每个信号归到哪一层。**这是唯一的一份**，页面和评分都读它。
SIGNAL_LAYER = {
    # 自己人
    "insider_buy":         "insider",
    "insider_sell":        "insider",
    "insider_cluster":     "insider",
    # 机构
    "survey_visit":        "institution",
    "survey_active":       "institution",
    "participation_spike": "institution",
    "inst_buying":         "institution",
    "inst_selling":        "institution",
    "analyst_upgrade":     "institution",
    "analyst_downgrade":   "institution",
    # 市场的钱
    "main_flow_in":        "money",
    "main_flow_out":       "money",
    "margin_surge_bull":   "money",
    "margin_surge_bear":   "money",
    "short_up":            "money",
    "short_down":          "money",
    "north_bound":         "money",
    # 价格自己
    "ma60":                "price",
    "ma250":               "price",
    "vwap60":              "price",
    "momentum_30d":        "price",
}


def layer_of(signal_key: str) -> str | None:
    """信号 → 层。没登记的返回 None —— **不猜**。

    宁可让新信号暂时不进分层视图，也不要默认塞进某一层：
    塞错层比不显示更糟，因为层的位置本身携带「有多可信、多快兑现」的含义。
    """
    return SIGNAL_LAYER.get(signal_key)


def layer_meta(layer_key: str) -> dict:
    return _BY_KEY.get(layer_key) or {}


def group_by_layer(signals: list) -> dict:
    """把一组 {key, direction, ...} 按层分组，保持 LAYERS 的顺序。"""
    out = {L["key"]: [] for L in LAYERS}
    for s in signals or []:
        lk = layer_of((s or {}).get("key", ""))
        if lk:
            out[lk].append(s)
    return out


def _layer_direction(sigs: list) -> str | None:
    """一层内部的合成方向。attention 不参与 —— 它没有方向可言（US-167）。

    同层多个信号同向 → 这一层的判断更可信；打平 → 这一层看不清。
    """
    bull = sum(1 for s in sigs or [] if (s or {}).get("direction") == "bull")
    bear = sum(1 for s in sigs or [] if (s or {}).get("direction") == "bear")
    if bull == bear:
        return None if bull == 0 else "mixed"
    return "bull" if bull > bear else "bear"


def layer_directions(by_layer: dict) -> dict:
    return {k: _layer_direction(v) for k, v in (by_layer or {}).items()}


def cross_layer_conflict(by_layer: dict) -> dict:
    """上下层打架 —— **方向不同，含义完全不同**。

    这正是用户妈妈遇到的情况：「华测检测是 A 级，为什么是看空预警？」
    她比的是第 0 层（公司本身）和第 3 层（市场的钱）。两者同时成立很正常，
    但页面从不解释，于是看起来像系统在自相矛盾。

    两种打架的含义是**相反**的，绝不能混为一谈：

      上层看多 + 下层看空 → 更懂的人在买、短期资金在走。可能是「还没传导到」
                            （机会），也可能是上层判断错了。至少不危险。
      上层看空 + 下层看多 → **自己人在撤，而市场的钱还在追**。这是最危险的
                            组合 —— 最懂的人先走，接盘的还没反应过来。

    返回 {} 表示不打架。
    """
    dirs = layer_directions(by_layer)
    upper = [k for k in ("insider", "institution") if dirs.get(k) in ("bull", "bear")]
    lower = [k for k in ("money", "price") if dirs.get(k) in ("bull", "bear")]
    if not upper or not lower:
        return {}
    ud, ld = dirs[upper[0]], dirs[lower[0]]
    if ud == ld:
        return {}
    if ud == "bull":
        return {
            "kind": "upper_bull_lower_bear", "severity": "watch",
            "upper": upper[0], "lower": lower[0],
            "text": f"更靠近公司的「{_BY_KEY[upper[0]]['short']}」偏正面，"
                    f"而「{_BY_KEY[lower[0]]['short']}」在往外走 —— "
                    f"可能是还没传导到，也可能是上面那层判断错了",
        }
    return {
        "kind": "upper_bear_lower_bull", "severity": "danger",
        "upper": upper[0], "lower": lower[0],
        "text": f"⚠️ 更靠近公司的「{_BY_KEY[upper[0]]['short']}」在撤，"
                f"而「{_BY_KEY[lower[0]]['short']}」还在进 —— "
                f"最懂的人先走、接盘的还没反应过来，这是最该小心的组合",
    }


def transmission_state(by_layer: dict) -> dict:
    """信息传到哪一层了 —— 这是整个分层的**用途**，不只是好看。

    返回 {reached, top, gap, story}
      reached: 有信号的层（按链序）
      top:     最靠上的那一层（最早知道的人）
      gap:     上层动了但下层还没动 → 真正的「领先」
      story:   一句人话

    上下打架时方向有含义：
      上层看多 + 下层看空 → 还没传导到（可能是机会，也可能上层错了）
      上层看空 + 下层看多 → **自己人在撤、散户在追**，最危险的组合
    """
    reached = [k for k in LAYER_ORDER if (by_layer or {}).get(k)]
    if not reached:
        return {"reached": [], "top": None, "gap": False, "story": ""}
    top = reached[0]
    has_price_layer = "price" in reached or "money" in reached
    # 「领先」= 上游有信号，而下游（钱/价格）还没跟上
    gap = top in ("insider", "institution") and not has_price_layer
    if gap:
        story = f"目前只有「{_BY_KEY[top]['short']}」这一层在动，钱和价格都还没跟上"
    elif top in ("money", "price"):
        story = "只有短期资金/价格在动，更靠前的几层还没有动静"
    else:
        story = "从上到下都有动静，信息已经在往价格传导"
    return {"reached": reached, "top": top, "gap": gap, "story": story}
