# US-121 Microservices 上线追踪

> 关了窗口看这个就知道进度到哪。设计见 PRODUCT.md 的 US-121。

## 背景一句话
旧 monolith `stock_pipeline.main()` 串行跑 100+ 只股票，2026-07-08 撞 120min timeout 被杀、一损俱损。
拆成 6 个独立服务（各自 workflow / 预算 / 失败告警 / service_runs 记账），根治「跑得稳 + 跑得少 + 分开失败」。
根因实测：Groq 瓶颈是 **TPM 12,000**（不是 RPM），并发无用 → 靠 **选择性分析 + token-bucket 配速**。

## 六大服务
| 服务 | 脚本 | workflow | 说明 |
|------|------|----------|------|
| fetch-svc | `scripts/svc_fetch.py` | `fetch-svc.yml` | 只抓数据(1a-1c3)不跑LLM，预算 FETCH_BUDGET_MIN |
| analyze-svc | `scripts/svc_analyze.py` | `analyze-svc.yml` | 选择性LLM(持仓/重大新闻/轮转)+配速+预算 |
| radar-svc | `scripts/svc_radar.py` | `radar-svc.yml` | 机构雷达+前兆信号(A股,AKShare密集) |
| digest-svc | `scripts/svc_digest.py` | `digest-svc.yml` | 快照commit+回填收益 |
| push-svc | `scripts/svc_push.py` | `push-svc.yml` | 读DB最新报告→推送，SKIP_PUSH开关 |
| material-svc | (复用 material_news_scan) | 待接 | 已有25min封顶 |

支撑：`radar_app/data/services.py`（service_run 上下文 + should_analyze）、`service_runs` 表、`scripts/groq_ratelimit.py`（TPM令牌桶）。

## 上线策略：并行双跑（strangler fig）
**合并 ≠ 切换。** 旧 monolith 继续当家、照常推妈妈；新服务先休眠+手动测几天自证，再逐个切，碰妈妈的(push)最后切。

---

## 进度清单

### 第 1 步：合并到 main（不碰任何 schedule）✅ 完成 2026-07-09
- [x] 合并 `us-121-microservices` → main (--no-ff) — merge commit 2708ae9
- [x] push main
- [x] 确认旧 cron.yml schedule 完好、5 个新服务 schedule=0（休眠）

### 第 2 步：并行观察（3–5 天，手动触发新服务）
每天核对：
- [ ] `fetch-svc` 手动跑 → service_runs 有 done 记录、价格新鲜
- [ ] `analyze-svc` 手动跑 → 只分析 ~10 只(选择性生效)、无 429、service_runs done
- [ ] `push-svc` SKIP_PUSH=1 → 生成内容正常、不真推
- [ ] `digest-svc` → 快照 commit 成功
- [ ] `radar-svc` → 前兆信号写 DB、AKShare 没被封
- [ ] **分开失败验证**：只跑 analyze-svc 且中途失败，确认 fetch/digest/push 仍独立成功
- [ ] 观察日志（记在下方「运行日志」）

### 第 3 步：确认稳了逐个切（一次一个，先不碰妈妈的）
- [x] fetch-svc 加 schedule（2026-07-12）：`0 7 * * 1-5`（07:00 UTC=15:00 CST 收盘，早于旧 monolith 08:00 UTC 1h 错峰）。旧 monolith 仍当家推妈妈，本服务只写 DB。观察一周稳定性。
- [x] analyze-svc 加 schedule（2026-07-29，US-138）：`0 8 * * 1-5`
- [x] digest-svc / radar-svc 加 schedule（2026-07-29，US-138）：`20 10` / `0 9`
- [ ] push-svc 加 schedule（**最后切，碰妈妈**）—— 待 SKIP_PUSH=1 云端验证通过
- [x] 关掉 cron.yml 里对应的旧 monolith 步骤（2026-07-29，US-138）
- [x] 旧 monolith 保留为手动回滚入口（`if: github.event_name == 'workflow_dispatch'`）

> ⚠️ **2026-07-29 事故：搁置 17 天的代价**
> 第 3 步只切了 fetch-svc 就停手，旧 monolith 继续当家 —— 而它从 **07-15 起
> 连续 10 个交易日崩在同一行**（`institutional_radar.py` 回购进度 `pct_done`
> 为 NaN → `int(NaN)`）。崩点之后的日报/`/report` 归档/Server酱 推送/新闻入库
> 全部陪葬，妈妈 10 天没收到推送。`Alert on failure` 依赖的
> `SERVERCHAN_ADMIN_KEY` 从未配置 → 全程静默。
> **这正是拆分要根治的一损俱损，但 monolith 没退休 = 隔离价值为零。**
> 收尾见 US-138。教训：strangler fig 停在半路，比不拆更危险 —— 新服务不当家
> 却让人以为已经拆完了。

### 第 4 步：孤儿步骤（US-138 补）
拆分时 6 件事没有任何服务接手，直接关 monolith 会静默消失：
- [x] 宏观快照 / 国际新闻 / 重大新闻扫描 → **market-svc（新建）**
- [x] 催化剂日历 → radar-svc
- [x] 持仓 Layer 2 量化评级 → analyze-svc（LLM 前先跑）
- [x] `/report` 日报归档 → push-svc（与推送同一份 digest）
- [x] rbnz / nzx_announcements / nzx_earnings → **不搬**，US-124 删掉
      `generate_report` 后零消费者，每天白抓

### 查 service_runs 的命令
```sql
SELECT service_name, started_at, status, duration_s, items_processed, stopped_early
FROM service_runs ORDER BY id DESC LIMIT 20;
```
云端触发：`gh workflow run <name>.yml --ref main -f <input>=<val>`

---

## 运行日志
（每次云端触发 / 观察结果记这里）

- 2026-07-09：分支 6 commit 完成，本地全部 smoke 测通过。
- 2026-07-09：合并 main（2708ae9）。首次云端触发 fetch-svc。
- 2026-07-09 云端 bug #1：Neon 无 service_runs 表（svc 漏 init_db）→ 修：各 svc 启动 init_db（1097273）。
- 2026-07-09 云端 bug #2（根因）：_run_with_timeout 用 ThreadPoolExecutor，超时后 shutdown(wait=True) 仍等卡死的 AKShare 线程 → fetch-svc 云端 14min 不停被取消。修：改 daemon 线程+join(timeout)，超时真生效（1b81a25）。**大概率也是旧 monolith 撞 2h 的元凶之一。**
- 2026-07-09 ✅ fetch-svc 重跑成功（run 28997948757）：预算真生效「达6min提前停,已6只」,软超时真中断「后台线程已抛下」,干净完成。bug#2 已修实锤。
- 2026-07-09 ⚠️ 重要发现：云端 ~60s/只（6只/6min）。AKShare 从 GitHub 美国 runner 极慢,1b/1c2 频繁撞步超时。131只一轮跑不完。**旧 monolith 老毛病(撞2h另一半原因)**。
  - 待议方案：①提高预算+多次跑靠缓存跳过(但news/fund_flow TTL=0每次重抓) ②China/Aliyun self-hosted runner ③AKShare走代理 ④接受轮转覆盖(配合选择性分析)
- 待办：触发 analyze-svc(走Groq不走AKShare,不受此影响)验证;throughput 单独解决。

---

## Throughput 治本设计（2026-07-10）

### 诊断：昨天修的是 bug，今天暴露的是性能瓶颈，两码事
修好超时 = 失败得干净，**不等于跑得快**。三个事实叠加：
1. **自伤 bug**：`svc_fetch.py` 调 `run_fetch_layers(force=True)` → `_is_stale` 直接 return True，**每只每次全量重抓**，7天TTL财务/24h技术面全被无视。「靠缓存跳过」的设想被这一行废掉。
2. news/fund_flow 的 `_CACHE_TTL=0`（pipeline_jobs.py:27-28）→ 交易日永远重抓，正是 AKShare 最慢且 A股专属的两层。
3. **根因是地理**：数据在中国（东财/新浪/THS），runner 在美国 GitHub，跨太平洋+地域限流 = 60s/只。Python 改不了 15000km。

### 三层治本
- **第1层 · 免费改** ✅ 2026-07-10：`svc_fetch.py` 改 `force=FORCE`（默认 False，`FORCE_FETCH=1` 可整库重建）。财务/技术面按 TTL 跳过，同日已抓的新闻·资金也跳 → 预算内多轮续跑真正靠缓存变快。
- **第2层 · 架构**（大部分已建）：fetch 带预算增量轮转 + analyze 只读DB永不碰AKShare。第1层生效后同日第二轮不重抓，即兑现「当日已抓就跳」。
- **第3层 · 基建（待拍板）**：A股采集搬到离数据近处。美股/港股/NZ 走 yfinance 从美国本来就快，不动。
  - 方案A（推荐）：阿里云香港 VPS ~$5/月挂 GitHub self-hosted runner，只跑 A股 fetch-svc，60s/只→1-3s/只，131只一轮跑完。代价：一台机器要维护，港区免ICP。
  - 方案B：不碰服务器，只做第1+2层，靠轮转覆盖+选择性分析，尾部A股信号可能滞后1-2天。零成本零运维。
  - 方案C：AKShare 走 HK 代理——AKShare 打太多端点，代理覆盖不全、易碎，不推荐。
  - **状态：用户拍板 B（不花钱）。→ 见 US-122。**

### US-122 优先级轮转 · 实现完成待云端验证（2026-07-10）
- `fetch_priority_codes()`（stocks.py）：持仓→观察→已卖出，同级按 stock_prices.fetched_at staleness 升序（NULLS FIRST，PG 兼容）。本地实测 137 只，9 只持仓排最前，持仓内最陈旧的 TWH.NZ 排第一 ✓。
- `svc_fetch.py` 换用它 + `FETCH_GAP_SEC=1.5s` 温柔串行（避东财封 IP）。commit 见 US-122。
- **待验证**：云端手动触发 fetch-svc → 看日志是否持仓先抓、预算耗尽时跳过的是长尾、gap 生效无封 IP。同日连跑两轮看第二轮是否只补长尾（依赖 US-121 force=False）。

### US-122 云端验证通过（2026-07-10，三轮实测）
| 指标 | 第1轮(3a86a6f) | 第2轮(+fallback) | 第3轮(+signals硬化) |
|------|------|------|------|
| 覆盖 | 50/134 | 52/134 | **124/134** |
| 1c2 资金超时 | ~31 | 31 | **1** |
| 主力资金成功 | 0（全 Connection aborted） | 49（新浪救） | 61（44 靠新浪） |
- **优先级轮转**：持仓（跨市场）按 staleness 排最前 ✓；第2轮美股价格刚更新排底部被跳过、自动轮到 A股长尾 ✓。失败的 fund_flow 未入库→仍判陈旧→下轮自动重试→新浪修好（优雅副作用）。
- **主力资金 fallback**：东财海外基本全挂（RemoteDisconnected），新浪 `MoneyFlow.ssi_ssfx_flzjtj` 补上，A股资金信号 0%→96%。
- **signals 快速失败+跨股缓存**：投行信号 3 个东财调用（质押/融资/机构持仓）原 hang 满 30s×31 只 → 8s 快速失败 + 融资明细按(市场,日期)跨股缓存 + 失败也缓存 None → cn 每只 30s→~4s，覆盖 50→124（2.5×）。
- **结论**：整个 watchlist 现在 ~1.3 轮刷完（原来撞预算永远跑不完）。B 方案（不花钱纯技术）达标。
- **待办**：US-121 第3步——给 fetch-svc 加 schedule（收盘后），观察一天再逐个切其余服务。
