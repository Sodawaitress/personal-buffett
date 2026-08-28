"""行业分析专栏 · 精选库（US-127）。

新增一篇 = 在 ARTICLES 加一条 + 放一个 templates/research/<slug>.html 自包含文章页。
精选，人工研究，不自动生成。
"""

ARTICLES = [
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
