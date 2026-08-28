"""把每日五选的推送正文解析成结构化数据（US-196）。

## 为什么要做

用户妈妈：「我这个是里面逃出来的这么多股票，然后这个网站又慢，
**有的信息就错过了**」。

而用户的洞察更关键：**「今日有什么值得看」不就是我们的今日五选** ——
问题不是要再造一个汇总页，是**五选只活在微信推送和 git 里，
网站上完全看不到**。微信一刷就过去了，回头找不着。

## 解析什么

`output/daily_push.txt` 由 Claude 在每日 routine 里写（US-191：
那是带 GitHub 连接的定时任务，不是对话）。格式固定：

    【今日五选】{日期}
    ━━ 今日主题 ━━
    {一句话}
    ━━ 1/{名称} ({代码}) {涨跌} ━━
    [公司底] ...
    [机构] ...
    [大众] ...
    今天的判断：...
    操作提示：...

## 一条纪律：解析失败就说失败，不猜

正文是人（Claude）写的自由文本，格式可能变。解析不出来时返回空 ——
**页面上宁可显示「今天的五选还没生成」，也不要显示半截错乱的内容**。
后者会让用户以为系统坏了，或者更糟：把残缺的分析当成完整的判断。
"""
import re

_HEAD = re.compile(r"【今日五选】\s*(\d{4}-\d{2}-\d{2})")
# ━━ 1/澜起科技 (688008) +10.06% ━━   或带后缀 · 新入库 · 入门鉴定
_ITEM = re.compile(
    r"━━\s*(\d+)\s*/\s*([^(（]+)[（(]\s*([0-9]{6}|[A-Z.]{2,10})\s*[）)]\s*"
    r"([+\-]?[0-9.]+%)?\s*(.*?)━━")
_THEME = re.compile(r"━━\s*今日主题\s*━━\s*\n(.+?)(?=\n━━|\Z)", re.S)
_LAYER = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


def parse(text: str) -> dict:
    """→ {date, theme, note, items:[{n,name,code,change,badge,layers,verdict,action}]}

    解析不出日期或一条都解析不出 → 返回 {}（**不猜**）。
    """
    if not text or "【今日五选】" not in text:
        return {}
    m = _HEAD.search(text)
    if not m:
        return {}
    date = m.group(1)

    theme = ""
    tm = _THEME.search(text)
    if tm:
        theme = tm.group(1).strip()

    # 标题行之前、主题之后的说明（如「本文基于 X 收盘数据」）
    note = ""
    head_end = m.end()
    pre = text[head_end:text.index("━━")] if "━━" in text[head_end:] else ""
    note = " ".join(x.strip() for x in pre.splitlines() if x.strip())

    marks = list(_ITEM.finditer(text))
    items = []
    for i, mk in enumerate(marks):
        body = text[mk.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        layers, verdict, action = {}, "", ""
        for ln in body.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            lm = _LAYER.match(ln)
            if lm:
                layers[lm.group(1)] = lm.group(2).strip()
            elif ln.startswith("今天的判断"):
                verdict = ln.split("：", 1)[-1].strip()
            elif ln.startswith("操作提示"):
                action = ln.split("：", 1)[-1].strip()
        items.append({
            "n": int(mk.group(1)),
            "name": mk.group(2).strip(),
            "code": mk.group(3).strip(),
            "change": (mk.group(4) or "").strip(),
            "badge": (mk.group(5) or "").strip(" ·"),
            "layers": layers,
            "verdict": verdict,
            "action": action,
        })
    if not items:
        return {}
    return {"date": date, "theme": theme, "note": note, "items": items}


def parse_file(path: str = "output/daily_push.txt") -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return parse(f.read())
    except Exception:
        return {}
