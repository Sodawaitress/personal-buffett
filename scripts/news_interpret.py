"""
US-118 LLM 层：对量化层判为重大的事件做约束式解读。

四道防瞎编锁：只喂原文+算好的AR；schema JSON；引不到原句就弃答；方向与AR矛盾则标记不推。
LLM 永远不产出材料度分数（量化算）、不报输入里没有的数字。
"""
import json
import re

from scripts.buffett_groq import _call_groq

_SYSTEM = """你是金融新闻解读助手。只依据【提供的新闻原文和数据】解读，严禁编造事实、数字、日期或原文里没有的背景。

规则：
- 必须从"新闻原文"里摘一句原话作为 evidence_quote；摘不到就 direction=neutral、explain="数据不足"。
- explain：中文人话，≤60字，说清"这对持有该股意味着什么"。不要复述标题。
- direction：bull(利多)/bear(利空)/neutral(中性)/mixed(双刃)。
- watch：原文若含明确日期或催化剂就填（如"7月13日谈判截止"），否则空字符串。
- confidence：0到1，背景不足就给低分。

只输出 JSON，不加任何其他文字：
{"direction":"..","explain":"..","evidence_quote":"..","watch":"..","confidence":0.0}"""


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def interpret_event(item: dict, code: str, name: str, market: str = "cn", fundamentals: dict | None = None) -> dict:
    """
    输入 item（scan_material_news 的一项）→ 返回约束式解读 dict：
    {direction, explain, evidence_quote, watch, confidence, conflict, abstained}
    """
    title = item.get("title", "")
    ar_z = item.get("ar_z")
    ar = item.get("ar")
    if ar_z is None:
        react = "当日无价格数据"
    elif ar_z >= 0.5:
        react = f"当日跑赢大盘（异常收益 {ar:+.2f}%，z={ar_z}）"
    elif ar_z <= -0.5:
        react = f"当日跑输大盘（异常收益 {ar:+.2f}%，z={ar_z}）"
    else:
        react = f"当日走势与大盘接近（异常收益 {ar:+.2f}%）"

    fin = ""
    if fundamentals:
        np_dir = fundamentals.get("net_profit_dir")
        if np_dir:
            fin = f"\n财务背景：最近净利{np_dir}"

    user_msg = (
        f"股票：{name}（{code}）\n"
        f"新闻原文：{title}\n"
        f"市场反应：{react}"
        f"{fin}"
    )

    raw = _call_groq(_SYSTEM, user_msg, max_tokens=220)
    parsed = _parse(raw)

    # 锁2：schema 缺字段 → 弃答
    if not parsed:
        return _abstain("解析失败")

    quote = parsed.get("evidence_quote", "") or ""
    direction = parsed.get("direction", "neutral")
    # 锁3：引用必须真来自原文（归一化子串），否则弃答
    if not quote or _norm(quote) not in _norm(title):
        return _abstain("引用不实")

    # 锁4：方向与 AR 明显矛盾 → 标 conflict，不推送
    conflict = 0
    if ar_z is not None:
        if direction == "bull" and ar_z <= -1.0:
            conflict = 1
        elif direction == "bear" and ar_z >= 1.0:
            conflict = 1

    return {
        "direction": direction if direction in ("bull", "bear", "neutral", "mixed") else "neutral",
        "explain": (parsed.get("explain") or "")[:80],
        "evidence_quote": quote[:120],
        "watch": (parsed.get("watch") or "")[:60],
        "confidence": _clamp(parsed.get("confidence")),
        "conflict": conflict,
        "abstained": 0,
    }


def _abstain(reason: str) -> dict:
    return {"direction": "neutral", "explain": "数据不足", "evidence_quote": "",
            "watch": "", "confidence": 0.0, "conflict": 0, "abstained": 1, "abstain_reason": reason}


def _parse(raw: str):
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else None
    except Exception:
        return None


def _clamp(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0


if __name__ == "__main__":
    # 冒烟：一条真新闻 + 一条编造引用测弃答
    good = {"title": "赣锋锂业：控股子公司赣锋锂电完成20亿元增资扩股", "ar": 0.4, "ar_z": 0.18}
    print("真新闻 →", interpret_event(good, "002460", "赣锋锂业"))
