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
- [ ] fetch-svc 加 schedule（收盘后），观察一天
- [ ] analyze-svc 加 schedule（fetch 后错峰）
- [ ] digest-svc / radar-svc 加 schedule
- [ ] push-svc 加 schedule（**最后切，碰妈妈**）
- [ ] 关掉 cron.yml 里对应的旧 monolith 步骤
- [ ] 旧 monolith 保留为手动回滚入口

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
- 待办：重跑 fetch-svc 验证 bug#2 已修（预算真能停）。
