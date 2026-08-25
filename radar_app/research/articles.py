"""行业分析专栏 · 精选库（US-127）。

新增一篇 = 在 ARTICLES 加一条 + 放一个 templates/research/<slug>.html 自包含文章页。
精选，人工研究，不自动生成。
"""

ARTICLES = [
    {
        # US-181：阿姨这几天连问五个问题，每个背后都是一条真的金融知识，
        # 而且每个都指出了系统一处真错误。写成科普，把「为什么这么改」讲给她听。
        "slug": "five-questions-2026",
        "title": "你问的五个问题，每一个都问对了",
        "subtitle": "信号怎么读 · 快慢与可信度 · 现象与知识",
        "cover": "🔍",
        "date": "2026-08-25",
        "template": "research/five-questions-2026.html",
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
