"""行业分析专栏 · 精选库（US-127）。

新增一篇 = 在 ARTICLES 加一条 + 放一个 templates/research/<slug>.html 自包含文章页。
精选，人工研究，不自动生成。
"""

ARTICLES = [
    {
        # US-212：写之前先查了文献，结果推翻了我自己的一个说法 ——
        # 「让盈利多跑」在美股有动量效应撑着，**在 A 股没有**
        # （研究显示短期 1-6 个月和长期 3 年都是反转，没有持久动量）。
        # 所以这篇里 A 股那一节是单独写的，不是把美股结论翻译一遍。
        #
        # 另外引用了 Morningstar「差 1.2 个百分点」那个数字的**反驳论文**
        # （CFA Institute 用同一份数据算出 0.10%，小十倍）——
        # 只引对自己论点有利的那一半，本身就是一种错误。
        "slug": "when-to-sell-2026",
        "title": "什么时候该卖",
        "subtitle": "一个有名字的冲动 · 证据 · 以及 A 股和美股的不同",
        "cover": "🚪",
        "date": "2026-09-14",
        "template": "research/when-to-sell-2026.html",
    },
    {
        # US-201：内部人买入的完整知识。写之前先查了文献（US-200），
        # 结果推翻了我自己拍的两个门槛 —— 所以文章里的数字都是有来源的，
        # 不是我编的。
        "slug": "insider-buying-2026",
        "title": "自己人买自家股票，什么时候才算数",
        "subtitle": "谁在买 · 买多少 · 什么时候看 · 现象与知识",
        "cover": "💰",
        "date": "2026-08-29",
        "template": "research/insider-buying-2026.html",
    },
    {
        # US-187：US-181 的重写。第一版把内容框在「你问的五个问题」上，
        # 但这个站不止一位用户在看，而这些困惑本来就是**普世**的 ——
        # 任何人打开一只股票的页面都会撞上「评级 A 却提示资金流出」。
        # 改成按「五种人在说话」组织，个人化的框架全部拆掉。
        "slug": "signal-layers-2026",
        "title": "一只股票，五种人在说话",
        "subtitle": "信号的快慢、可信度，和它们为什么看起来在打架",
        "cover": "🔍",
        "date": "2026-08-27",
        "template": "research/signal-layers-2026.html",
    },
    {
        "slug": "cancer-vaccine-2026",
        "title": "癌症疫苗来了？涨的那只，正是系统让你减持的",
        "subtitle": "创新药 · 融券读法 · 现象与知识",
        "cover": "💉",
        "date": "2026-08-23",
        "template": "research/cancer-vaccine-2026.html",
    },
    {
        "slug": "base-and-sprint-2026",
        "title": "稳稳保底 · 放心冲刺：无忧做短线",
        "subtitle": "投资心法 · 仓位分法",
        "cover": "🛡️",
        "date": "2026-07-22",
        "template": "research/base-and-sprint-2026.html",
    },
    {
        "slug": "ai-chip-selloff-2026",
        "title": "AI 芯片大跌复盘：机构在派发，别追刀口",
        "subtitle": "半导体 · 光通信 · 行业研究",
        "cover": "📉",
        "date": "2026-07-21",
        "template": "research/ai-chip-selloff-2026.html",
    },
    {
        "slug": "milk-tea-2026",
        "title": "上市奶茶六强：谁在赚钱，谁被价格战碾碎",
        "subtitle": "中国新茶饮 · 行业研究",
        "cover": "🧋",
        "date": "2026-07-13",
        "template": "research/milk-tea-2026.html",
    },
]


def list_articles():
    return sorted(ARTICLES, key=lambda a: a["date"], reverse=True)


def latest_article():
    items = list_articles()
    return items[0] if items else None


def get_article(slug):
    return next((a for a in ARTICLES if a["slug"] == slug), None)


# ── US-215：文章写完了，没人知道 ──────────────────────────────────────
#
# 站上 7 篇专栏，**一篇都没通知过读者**。微信推送只在
# `output/daily_push.txt` 变动时触发（见 wechat-push.yml），
# 而 daily_push 从来没提过文章 —— 它们写完、部署、然后躺着等人自己发现。
#
# 用户问「文章发了吗」的时候，答案是：上线了，但没发出去。
# 这和 US-212 那句「讲过 ≠ 发出去」是同一件事再发生一次，只是更深一层：
# **发布 ≠ 送达。**
#
# 修法不开第二条推送通道（US-150 的教训：并行通道 = 读者收到重复推送），
# 而是把「有哪几篇还没通知过」**算好塞进快照**，让 Routine 不可能漏掉。
# 沿用 US-166 的判断：本仓所有沉默失败都证明「靠自觉」不成立。

ANNOUNCED_PATH = "knowledge/announced_articles.txt"
_MAX_PER_PUSH = 2          # 一次最多提两篇，攒了一堆时不刷屏


def _announced() -> set:
    try:
        with open(ANNOUNCED_PATH, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()
                    and not ln.startswith("#")}
    except FileNotFoundError:
        return set()


def unannounced(limit: int = _MAX_PER_PUSH) -> list:
    """还没在 daily_push 里提过的文章，最新的在前。"""
    seen = _announced()
    return [a for a in list_articles() if a["slug"] not in seen][:limit]


def mark_announced(slugs) -> int:
    """提过之后记一笔。忘了记 → 会重复提，**烦但不危险，而且看得见**
    （比静默漏掉好）。"""
    import os
    seen = _announced()
    new = [s for s in slugs if s and s not in seen]
    if not new:
        return 0
    os.makedirs(os.path.dirname(ANNOUNCED_PATH) or ".", exist_ok=True)
    with open(ANNOUNCED_PATH, "a", encoding="utf-8") as f:
        for s in new:
            f.write(s + "\n")
    return len(new)
