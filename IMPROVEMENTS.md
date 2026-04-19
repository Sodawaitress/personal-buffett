# 改进清单

与 COMP639 Piwakawaka 项目对比后整理，下次打开时参考。

---

## 1. SQLite → PostgreSQL（高优先级）

**为什么：** SQLite 多用户并发写入会锁表，未来如果分享给多人使用会有问题。

**怎么做：**
- 安装 psycopg2，替换 sqlite3 连接
- 参考 Piwakawaka 的 `connect.py` + `db.py`（Flask `g` + `teardown_appcontext` 自动关闭连接）
- 数据迁移：sqlite3 导出 CSV → 导入 PostgreSQL

---

## 2. 细化权限系统 RBAC（高优先级）

**为什么：** 目前只有 admin/subscriber 两级，粒度太粗。AI 分析功能应该只对特定用户开放（保护 Groq 免费额度）。

**怎么做：**
- 参考 Piwakawaka 的组合装饰器模式：`@role_required('admin', 'pro')`
- 新增 Pro 用户等级，只有 Pro 才能触发 Groq AI 分析
- 普通用户只能看规则打分（QuantitativeRater fallback）

---

## 3. Watchlist 多条件筛选 SQL（中优先级）

**为什么：** 当前筛选逻辑散乱，多个条件叠加时容易出 bug。

**怎么做：**
- 使用 `WHERE 1=1` 动态拼接模式，按需 `AND` 追加条件
- 示例来自 Piwakawaka US15（按线路/物种/饵料/日期过滤 catch 记录）

```python
query = "SELECT * FROM stock WHERE 1=1"
params = []
if status:
    query += " AND status = %s"
    params.append(status)
if market:
    query += " AND market = %s"
    params.append(market)
```

---

## 4. 自动化测试补全（中优先级）

**为什么：** 现有 smoke tests 覆盖不够，核心评分逻辑（QuantitativeRater 各框架）没有边界值测试。

**怎么做：**
- 给每个 framework 路由（成长股/周期股/金融股/公用事业）写 pytest 单元测试
- 重点测试边界值：PE 极高/极低、ROE 负值、数据缺失时的 fallback 行为

---

## 5. .env 配置管理（中优先级）

**为什么：** 目前敏感配置（API key、DB 密码）散落在代码里，部署到不同环境需要手动改。

**怎么做：**
- 已有 `.env.example`，确保所有环境变量都走 `os.getenv()` 读取
- 本地开发、Oracle Cloud、PythonAnywhere 各维护独立的 `.env` 文件
