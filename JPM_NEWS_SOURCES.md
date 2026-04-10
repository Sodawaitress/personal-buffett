# 摩根大通新闻源集成方案

## 当前状态 (2026-04-10)

### ✅ 已完成
- [x] 添加摩根大通作为新闻源（`JPMORGANCHASE_SOURCES`）
- [x] 集成到 `stock_pipeline.py` 的数据流
- [x] 添加英文关键词库用于分析 JPM 英文新闻
- [x] 在 `_analyze_news_signals()` 中支持英文情绪分析

### ⚠️ 当前问题

#### 1. RSS Feed 地址失效
```python
JPMORGANCHASE_SOURCES = [
    ("https://www.jpmorganchase.com/en/about/news/rss.xml", "摩根大通新闻"),     # ❌ 404
    ("https://research.jpmorgan.com/c/feeds", "摩根大通研究"),                    # ❌ DNS 失败
]
```

**原因**: 这两个 URL 已被 JPMorgan 从网站移除或重新定向

---

## 可用的 JPMorgan 新闻源

### 选项 A: Google News RSS (推荐)
Google News 提供了关于 JPMorgan 的 RSS Feed：
```python
JPMORGANCHASE_SOURCES = [
    ("https://news.google.com/rss/search?q=JPMorgan%20earnings%20analysis&hl=en&gl=US&ceid=US:en", "JPMorgan 投资分析"),
    ("https://news.google.com/rss/search?q=JPMorgan%20stock%20rating&hl=en&gl=US&ceid=US:en", "JPMorgan 股票评级"),
]
```

**优点**: 稳定、包含多个来源、自动聚合
**缺点**: 通用新闻，可能包含噪音

### 选项 B: 直接爬取 JPMorgan 官网
JPMorgan 新闻可在此获取：
- 主新闻: https://www.jpmorganchase.com/en/about/news
- 研究报告: https://www.jpmorgan.com/insights

**需要**: BeautifulSoup + 定期维护 CSS 选择器

### 选项 C: JPMorgan HK Warrants 门户 (新发现)
```
https://www.jpmhkwarrants.com/zh_hk/market-statistics/news
```

**结构**:
- 动态加载（AJAX）
- API 端点: `/zh_hk/ajax/newsfeed-result/scategory/{category}/page/{page}/noPerPage/{limit}`
- 新闻标题在 `<div class="tl">` 中
- 包含 HK 市场相关新闻

**优点**: 专注于港股、权证信息
**缺点**: 仅港股相关，需要 HTML 爬取

---

## 推荐方案

### 短期 (立即)
保持当前 JPM RSS 源配置为空，依赖 Google News 全局搜索：
- Google News 已包含 JPMorgan 相关新闻
- 用户通过 `INTL_QUERIES` 中的英文查询也会获取 JPM 分析

### 中期 (1-2 周)
1. 实现 BeautifulSoup 支持
2. 添加官方 JPMorgan 新闻爬虫
3. 可选：添加 HK Warrants 门户

### 长期
- 建立 JPMorgan 企业 API 对接（如可用）
- 多语言新闻源聚合

---

## 代码更改

### 立即修复：移除失效的 RSS URL

在 `scripts/stock_fetch.py` 第 718-721 行：

```python
# ── 新闻源配置 ────────────────────────────────────────
# 摩根大通研究报告 RSS (目前无效，等待替换)
JPMORGANCHASE_SOURCES = []  # 空列表，暂时禁用

# 注意: JPMorgan 新闻通过以下方式获取:
# 1. Google News 全局搜索 (INTL_QUERIES)
# 2. 英文关键词分析已在 _analyze_news_signals() 中支持
```

**理由**: 
- 防止日志中出现错误（HTTP 404、DNS 失败）
- 保留功能结构，便于未来添加有效来源
- 英文新闻分析已通过 INTL_QUERIES 的 Google News 实现

---

## 验证检查表

- [ ] 删除或注释失效的 JPMorgan RSS URL
- [ ] 确认 INTL_QUERIES 包含 JPMorgan 相关查询
- [ ] 测试英文新闻分析（sentiment 识别）
- [ ] 确认数据库中摩根大通新闻被正确标记
- [ ] 更新本文档为已验证状态

---

## 附录：HK Warrants Portal 爬虫示例

如需未来实现，参考代码框架：

```python
def fetch_jpmhk_warrants_news() -> list:
    """从 JPMorgan HK Warrants 门户爬取新闻"""
    import requests
    import re
    
    items = []
    url = "https://www.jpmhkwarrants.com/zh_hk/ajax/newsfeed-result/scategory/hongkong/page/1/noPerPage/10"
    
    try:
        resp = requests.get(url, timeout=5)
        
        # 提取日期
        dates = re.findall(r'<span class="date">([^<]+)</span>', resp.text)
        
        # 提取标题
        titles = re.findall(r'<div class="tl">([^<]+)</div>', resp.text)
        
        # 提取摘要
        summaries = re.findall(r'<div class="collapse">\s*([^<]+)', resp.text)
        
        for i, title in enumerate(titles):
            items.append({
                "title": title,
                "summary": summaries[i][:200] if i < len(summaries) else "",
                "date": dates[i] if i < len(dates) else "",
                "source": "JPMorgan HK Warrants",
                "link": "",  # 需要解析完整链接
            })
        
        return items
    except Exception:
        return []
```

需要添加依赖: `pip install beautifulsoup4 lxml`
