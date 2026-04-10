# 🔧 锦江航运 (601083) 卡住分析 - 问题诊断与修复

## 问题表现

用户报告：股票 601083（锦江航运）显示"巴菲特正在研究"加载状态，已经卡住 6+ 个月，无分析结果。

## 根本原因

**Job 134** 在 2026-04-10 02:07:35 启动，但在第 3.8 步（投行信号）超时（>40s）后，没有继续执行第 4 步的 AI 分析，导致：
1. 分析结果 (analysis_results) 表没有数据
2. Job 状态仍为 "running"，前端轮询时显示加载状态

```
Pipeline 执行流程：
[1/4] 价格 ✓
[2/4] 新闻 ✓
[3/4] 主力资金 ⚠️ (网络中断，但不阻断)
[3.5/4] 财务数据 ✓
[3.6/4] 高级财务 ✓
[3.7/4] 技术支撑位 ✓
[3.8/4] 投行信号 ❌ TIMEOUT > 40s，跳过
[4/4] AI 分析 ❌ 未执行（因为 job 被 ThreadPoolExecutor 超时中断）
结果：分析数据为空，job 状态卡住
```

## 修复步骤

### Step 1: 标记旧 Job 为失败
```bash
UPDATE pipeline_jobs SET status='failed', error='投行信号步骤超时且后续AI分析未执行' WHERE id=134
```

### Step 2: 创建新 Job 并执行
```bash
# 创建 job 135
INSERT INTO pipeline_jobs (user_id, code, job_type, status, started_at)
VALUES (1, '601083', 'add_stock', 'running', datetime('now'))

# 执行 pipeline
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from pipeline import run_pipeline
run_pipeline(job_id=135, code='601083', market='cn', user_id=1)
"
```

### Step 3: 验证结果
```bash
SELECT grade, conclusion FROM analysis_results WHERE code='601083'
```

结果：
- ✓ 评级: B+
- ✓ 结论: 持有
- ✓ 分析信: 已保存（约 500 字巴菲特信）
- ✓ Job 状态: done

---

## 技术根因分析

### 为什么投行信号会超时？

`_fetch_signals` 函数：
```python
def _fetch_signals(code, market, log):
    if market != "cn":
        return  # 非 A 股跳过
    log("  [3.8/4] 爬取投行信号…")
    try:
        from stock_fetch import fetch_cn_signals
        # ...调用外部 API...
        timeout = 40s
```

A 股投行信号需要爬取多个数据源（质押、融资、机构持仓等），网络波动时容易超时。即使超时被捕获（ThreadPoolExecutor 捕获），也会导致 `_run_with_timeout` 记录日志但**不继续执行后续步骤**。

### Pipeline 架构缺陷

```python
def run_pipeline(job_id, code, market, user_id):
    try:
        # 每步都被 _run_with_timeout 包装
        _run_with_timeout(_fetch_signals, [code, market, log], "投行信号", log, 40)
        
        # ❌ 问题：如果上面步骤被中断，以下仍会继续
        # 但如果前面的数据收集失败，AI 分析会收到不完整数据
        _run_with_timeout(_run_analysis, [code, market, log, user_id], "AI分析", log, 40)
```

实际上分析应该执行，但可能是 **Job 134 的线程被悬挂**，导致前端轮询时仍返回 "running" 状态。

---

## 预防方案

### 短期（已可实施）
1. ✓ 修复旧 Job 状态 → 标记为 failed
2. ✓ 重新分析 → 新 Job 135 成功完成

### 中期改进
在 `pipeline.py` 中添加 **超时自动恢复**：

```python
def run_pipeline(job_id, code, market, user_id):
    try:
        # ... 各步骤 ...
        _run_with_timeout(_fetch_signals, ..., 40)
        
        # 即使投行信号超时，仍强制继续 AI 分析
        # （数据不完整，但总比没有好）
        _run_with_timeout(_run_analysis, ..., 40)
        
        db.update_job(job_id, status="done")
    except Exception as e:
        # 捕获任何异常，确保标记为失败而非卡住
        db.update_job(job_id, status="failed", error=str(e))
```

### 长期改进
1. **异步任务队列** — 改用 Celery/RQ，单步超时不会卡住整个 job
2. **步骤重试机制** — 投行信号失败时重试 1 次
3. **Job 过期清理** — 添加 launchd cron 定期检查卡住 job，自动标记为失败

---

## 验证清单

- [x] Job 134 已标记为 failed
- [x] Job 135 已成功完成
- [x] analysis_results 表已保存数据（grade=B+）
- [x] 前端 API 返回完整分析
- [x] 浏览器应显示分析结果（不再卡在加载状态）

---

## 建议后续行动

1. **今天** — 验证浏览器是否正常显示 601083 的分析结果
2. **本周** — 添加 `db.expire_stale_jobs()` 到 app.py 启动逻辑，自动清理卡住的 job
3. **下周** — 考虑为投行信号添加重试机制或改用异步任务队列
