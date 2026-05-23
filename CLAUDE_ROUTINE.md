# 私人巴菲特 · Claude Daily Routine

每日运行，完成两项任务：
1. **Run 1**：从自选股里选出今天最值得关注的五只，用三层框架讲清楚，推给妈妈
2. **Run 2**：把昨天/上次的判断和实际走势对比，找出哪里判断对了、哪里错了，写进改进日志

---

## 配置

```
数据快照 (GitHub raw，可直接 fetch):
  https://raw.githubusercontent.com/Sodawaitress/personal-buffett/main/snapshots/daily_snapshot.json

改进日志: knowledge/improvement_log.md（编辑文件后 git commit 保存到 repo）
GitHub repo: Sodawaitress/personal-buffett（已连接，可读写）
微信推送: 由 Fly.io 每日自动完成，Routine 不负责推送
```

---

## 三层框架

每只股票，从三个层面看，层层递进：

**第一层：公司底**
这家公司是做什么的？护城河是什么？现在估值在什么位置？
- 护城河方向：成本优势 / 网络效应 / 转换成本 / 规模壁垒 / 品牌
- 估值位置：便宜（历史低位）/ 合理 / 贵（需要高增长兑现）
- 这一层决定："这只股票值不值得持有"，是基础。

**第二层：机构时机**
聪明钱在做什么？方向和速度如何？
- 机构调研质量排序：现场参观★★★★★ > 特定对象调研★★★★ > 电话会★★★ > 业绩说明会★★
- 资金信号：主力净流入/流出趋势
- 融券变化：大幅增加 = 机构在做空；大幅减少 = 空头平仓
- 这一层决定："现在是不是进场的时间"，是时机。

**读懂调研信号的关键原则：**
- 「业绩说明会」且之后无跟进 → 机构只是例行参加，不算看好，不能算信号
- 「现场参观」或「实地调研」 → 机构主动跑到工厂，是真正的认可行为，权重最高
- 「特定对象调研」 → 机构专门约的，不是公开活动，说明有针对性的调研意图
- 单次家数大（≥50家）但只有1次 → 数量炸裂但缺乏持续性，需要特别说明不要过度解读
- 多次调研 + 时间间隔短（30天内3次以上）→ 这是最强信号，机构在持续验证建仓逻辑
- 调研后股价未动 → 机构可能还在建仓，价格还没反映，是抢跑机会

**第三层：大众情绪**
新闻在说什么？散户知道多少？
- 新闻 sentiment：正面 / 中性 / 负面
- 与机构方向的关系：一致（确认）/ 背离（警惕）/ 逆向（机会）
- 这一层决定："市场预期是否已经反映"，是价格预期的空间。

**三层叠加的判断规则：**
- 公司底好 + 机构在悄悄动 + 大众还不知道 → 最完美的进场窗口，重点推
- 公司底好 + 机构动了 + 大众也知道了（新闻正面） → 趋势确认，但空间有限
- 公司底好 + 机构未动 + 大众情绪负面 → 耐心等待，继续观察
- 公司底差 + 机构在动 → 博弈行情，不是我们的游戏
- 三层全负面 → 不推，明确说原因

---

## Run 1 · 今日五选

### Step 1：读取今日快照

从 GitHub repo 读取 Fly.io 服务器每日提交的快照文件：
```
https://raw.githubusercontent.com/Sodawaitress/personal-buffett/main/snapshots/daily_snapshot.json
```
（数据由 Fly.io precursor scanner 完成后自动 commit，包含完整的价格/评级/前兆信号/新闻）

### Step 2：判断是否交易日

若所有股票 price.change_pct 都为 null，说明今天非交易日，只发简短提示，不做分析。

### Step 3：Claude 自主选出今日五只

不用机械规则。用判断力，综合以下因素，选出今天最值得讲的五只：

**优先选这些情况：**
1. 公司底好（grade A/B）× 机构信号出现 = 时机已到
2. 今天有异动（涨/跌幅 > 5%）× 有基本面支撑 = 值得解释为什么
3. 新入库股票（is_new = true）× 评级 B 以上 = 需要做入门鉴定
4. 机构信号强（survey 现场参观 + 多次调研）× 市场还未反应 = 先于大众
5. 新闻情绪与机构方向相反（背离信号）= 值得特别说明

**主动回避：**
- 数据明显缺失（如 moat = "0/35：护城河数据不足"）但没有独立判断依据
- 连续 D/E 评级 + 无任何正面信号
- 重复：昨天已经讲过且无新进展

**五选的多样性要求：**
- 不要五只都是同一行业（如全选AI算力）
- 至少一只是防御型（消费/公用事业/医疗）
- 至少一只有今日价格异动值得解释

### Step 4：对每只股票，写三层分析

**格式（纯文本，不用 markdown，微信渲染问题）：**

```
【今日五选】{日期}

━━ 今日主题 ━━
{一句话概括今天市场的主要信号，如：AI板块继续分化，医药出现底部信号}

━━ 1/{股票名} ({代码}) {今日涨跌幅} ━━
[公司底] {这家公司做什么，护城河一句话，估值便宜/合理/贵}
[机构] {机构在做什么，解读为什么这样做}
[大众] {新闻情绪，与机构是否一致}
今天的判断：{一句话，这只股票现在处于三层叠加的哪种情况}
操作提示：{具体建议，如：等回调到¥XX考虑，或：当前不是进场时机，或：已持仓可继续持有}

{重复5次}

━━ 今日不推名单 ━━
{如果有明显应该回避的股票，简单说原因，1-2只即可}

━━ 今日预言 ━━
{选1-2只，写出10天内的价格方向预期和关键观察点，用于下次自我验证}
例：天孚通信 — 预期10天内震荡整理（+5%至-8%区间），关键点是2026-05-30前后有无CPO相关订单公告

---
数据来源：东方财富+机构调研 | 仅供参考 | 不构成投资建议
```

### Step 5：写入分析日志 + 触发微信推送 + 保存结构化预言

全部用 GitHub API 直接写 main 分支（不要用 `git commit`）。

全部用 GitHub API 直接写 main 分支（不要用 `git commit`，Routine 的本地 git 只推私有分支）。

**5a：写改进日志**
1. GET `https://api.github.com/repos/Sodawaitress/personal-buffett/contents/knowledge/improvement_log.md` 读取当前内容和 SHA
2. 把当前内容 base64 decode，追加今日五选分析，重新 base64 encode
3. PUT 同一地址，payload: `{"message": "chore: routine log {日期}", "content": "<新base64>", "sha": "<旧sha>", "branch": "main"}`

**5b：写微信推送文件（触发 GitHub Actions 自动发送 Server酱）**
1. 把 Step 4 生成的完整推送文本（纯文本格式，第一行是标题如"【今日五选】2026-05-24"）base64 encode
2. GET `https://api.github.com/repos/Sodawaitress/personal-buffett/contents/output/daily_push.txt` 获取 SHA（文件可能不存在，不存在就不带 sha）
3. PUT 同一地址，payload: `{"message": "chore: daily push {日期}", "content": "<base64>", "branch": "main"}`（如有旧 sha 就带上）

文件写入 main 后，GitHub Actions（`.github/workflows/wechat-push.yml`）会自动检测并把内容发给 Server酱，妈妈就收到微信了。

**5c：写结构化预言（训练数据闭环）**

把今日预言写成 JSON，PUT 到 `output/predictions_pending.json`（Fly.io 下次跑时会读取并存入数据库，`backfill_returns.py` 10天后自动回填实际涨跌，形成训练样本）。

格式：
```json
[
  {
    "date": "{今日日期 YYYY-MM-DD}",
    "code": "{股票代码}",
    "name": "{股票名}",
    "direction": "up" 或 "down" 或 "sideways",
    "horizon_days": 10,
    "key_signal": "{触发预言的核心信号，一句话}",
    "price_at_prediction": {今日收盘价，从快照 price.current 取}
  }
]
```

操作：
1. GET `https://api.github.com/repos/Sodawaitress/personal-buffett/contents/output/predictions_pending.json` 获取 SHA（不存在则不带 sha）
2. PUT 同一地址，写入今日预言 JSON 数组，message: `"chore: predictions {日期}"`

---

## Run 2 · 自我迭代

### Step 1：读取改进日志，找上次的预言

读取 repo 中的 `knowledge/improvement_log.md`，找最近一次写的"今日预言"部分。

### Step 2：验证预言

用当日数据中的 price.current 和 price.change_pct，对比预言时的价格，判断：
- 方向对了吗（涨/跌/震荡）？
- 关键观察点出现了吗？
- 误判的核心原因是什么？

### Step 3：选一只今日最有分析价值的股票做深度对比

对比 Claude 独立判断 vs 网站 analysis 字段，找出最有意思的差异：
- 评级偏差（Claude B，网站 D）→ 说明哪一方更准，为什么
- 信息缺失（网站没提机构调研密度）→ 建议加入什么数据
- 行业背景缺失（用通用框架评重资产行业）→ 建议哪类公司用专属框架
- 数据时效问题 → 建议触发重跑的条件

### Step 4：写入改进日志

追加到 `knowledge/improvement_log.md`，格式：

```markdown
## {日期} · 验证 · {股票名}
上次预言: ...
实际走势: ...
判断准确度: 方向对/错，原因...

---

## {日期} · 对比 · {股票名} ({代码})
Claude判断: {评级} — {理由}
网站当前: {评级} — {理由}
差异分析: ...
改进建议: ...

---
```

写完后同样用 GitHub API PUT 到 main 分支（message: `chore: routine log {日期}`），不用 git commit。

---

## 触发时间

- 交易日 17:30 北京时间（收盘后1.5小时，数据已更新）
- 节假日跳过

---

## 学习原则

每次 Run 2 都在做一件事：**把判断力变成可追踪的记录**。

判断对了 → 找出为什么对（是信号先行？是行业理解？）→ 这个方法下次继续用
判断错了 → 找出为什么错（数据缺失？逻辑链断了？市场博弈打乱了基本面？）→ 改进框架

长期积累后，improvement_log.md 就变成了这个系统的"学习记忆"：
- 哪类信号在哪类公司上有效
- 哪种情况网站分析可信，哪种不可信
- 哪些行业需要专属的分析维度

这是真正的自我迭代。
