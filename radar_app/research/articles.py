"""行业分析专栏 · 精选库（US-127）。

新增一篇 = 在 ARTICLES 加一条 + 放一个 templates/research/<slug>.html 自包含文章页。
精选，人工研究，不自动生成。
"""

ARTICLES = [
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
