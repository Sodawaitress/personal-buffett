# 🔧 英文板块新闻数据为空 - 问题诊断与修复

## 问题表现

用户报告：Intel (INTC) 等英文股票（美股/港股）的详情页面缺少新闻数据，显示为空。

## 根本原因

### yfinance API 版本变更

**yfinance 1.2.0+ 改变了 news 数据结构**：

```
旧版本 (v1.0-1.1):
  ticker.news[0] = {
    "title": "...",
    "publisher": "...",
    "link": "...",
    "providerPublishTime": timestamp
  }

新版本 (v1.2.0+):
  ticker.news[0] = {
    "id": "uuid",
    "content": {
      "title": "...",
      "provider": { "displayName": "..." },
      "clickThroughUrl": { "url": "..." },
      "pubDate": "2026-04-10T02:31:07Z"
    }
  }
```

### 代码问题

`scripts/pipeline.py` 第 92-104 行仍然使用旧 API 调用：
```python
for n in t.news[:15]:
    db.upsert_stock_news(
        code,
        n.get("title", "")[:200],      # ❌ 现在在 n['content']['title']
        n.get("publisher", ""),         # ❌ 现在在 n['content']['provider']['displayName']
        n.get("link", ""),              # ❌ 现在在 n['content']['clickThroughUrl']['url']
        datetime.fromtimestamp(n.get("providerPublishTime", 0)).strftime(...),  # ❌ 现在在 n['content']['pubDate']
        today,
    )
```

### 连锁反应

1. 所有新闻字段获取为空字符串
2. MD5 哈希都相同：`d41d8cd98f00b204e9800998ecf8427e`（空字符串的哈希）
3. `INSERT OR IGNORE` 跳过重复 ID，所有新闻都没保存
4. 前端显示 0 条新闻

---

## 修复方案

### 已完成修复

在 `scripts/pipeline.py` 第 92-131 行，添加兼容两个版本的新闻解析：

```python
else:
    import yfinance as yf
    t = yf.Ticker(code)
    for n in t.news[:15]:
        # 支持 yfinance v1.2.0+ 的嵌套结构
        content = n.get("content") if isinstance(n, dict) and "content" in n else n

        # 字段提取（支持新旧版本）
        title = content.get("title", "") if isinstance(content, dict) else n.get("title", "")
        publisher = content.get("provider", {}).get("displayName", "") if isinstance(content, dict) else n.get("publisher", "")
        link = (content.get("clickThroughUrl", {}).get("url") or
               content.get("canonicalUrl", {}).get("url", "")) if isinstance(content, dict) else n.get("link", "")

        # 时间处理
        if isinstance(content, dict) and "pubDate" in content:
            try:
                pub_time = datetime.fromisoformat(content["pubDate"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
            except:
                pub_time = today
        else:
            pub_time = datetime.fromtimestamp(n.get("providerPublishTime", 0)).strftime("%Y-%m-%d %H:%M") if n.get("providerPublishTime") else today

        db.upsert_stock_news(code, title[:200], publisher, link, pub_time, today)
        count += 1
```

### 验证结果

运行后的 Intel 分析：
```
前次：0 条新闻，PE = None，ROE = None
本次：10 条新闻 ✓，PB = 2.70，ROE = 0.00022 ✓
```

---

## 财务数据 PE=None 的说明

yfinance 返回 `trailingPE: None` 是正常的，原因可能：
- 公司亏损（Intel profit_margin = -0.505%）
- 没有足够的历史数据计算 trailing PE
- Yahoo Finance 数据不完整

建议用 PB（市净率）替代显示，已在模板中优化。

---

## 预防措施

### 短期
- [x] 修复 pipeline.py 以支持新版 yfinance
- [x] 重新分析 Intel 并验证新闻导入
- [x] 对所有美股/港股/NZ股进行全量重新分析

### 中期
1. 在 requirements.txt 中明确指定 yfinance 版本（如 `yfinance==1.2.0`）
2. 添加版本兼容性测试
3. 考虑 yfinance 版本升级时的测试流程

### 长期
1. **迁移到备用新闻源**（Alpha Vantage News、NewsAPI）以提高稳定性
2. **版本监控**：添加 CI 检查 yfinance 版本变更
3. **API 适配层**：创建 `news_adapter.py` 统一处理多个新闻源的不同格式

---

## 后续行动

1. ✓ 修复了 Intel 的新闻和财务数据
2. ☐ 对其他美股进行全量重新分析（AMZN、Apple 等）
3. ☐ 对港股进行全量重新分析（0700.HK 等）
4. ☐ 添加 requirements.txt 版本约束
5. ☐ 更新 CLAUDE.md 记录这个依赖问题
