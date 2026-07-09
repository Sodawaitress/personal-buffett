# 钱的游戏规则 · 研究记录

> 目标：人一生中必须要学习的真正有用的数学——做成高忠诚度游戏。
> 研究日期：2026-06-14

---

## 一、市场现有产品分析

### Prodigy Math
- **核心循环**：战斗 → 解数学题（攻击机制）→ 奖励 → 新地图
- **关键洞见**：数学是攻击动作本身，不是关卡之间的小测验。玩家不觉得自己在学数学。
- **数据**：2M 日活，每天 2000 万道题
- **局限**：教的是算术，不是金融数学
- 🔗 https://aws.amazon.com/blogs/publicsector/gamifying-math-education-how-prodigy-uses-aws-to-scale-and-process-20-million-questions-daily/
- 🔗 https://trophy.so/blog/prodigy-math-game-gamification-case-study

### Cashflow 101（Rich Dad Poor Dad 配套桌游）
- **核心循环**：每回合填写真实财务报表 → 鼠圈跑道（低收入，靠工资）vs 快车道（被动收入）→ 逃出鼠圈
- **关键洞见**：把「逃离鼠圈」这个抽象概念变成可以身体感受的体验，概念迁移率高
- **局限**：单次游戏 3-4 小时，重复可玩性低
- 🔗 https://en.wikipedia.org/wiki/Cashflow_101

### 已有产品的空缺
Prodigy 教算术，Cashflow 教金融概念。**没有产品做到：把个人真实决策和数学实时连接**。这是我们的位置。

---

## 二、什么数学真正改变人的行为

### 研究结论（重要）
NEFE/FINRA 跨 76 国研究（2022）：**在决策发生的瞬间**出现的计算，效果远大于提前上的财务课。
- 提前学财务知识 → 行为改变很小
- 在做决策时看到数学 → 改变显著

🔗 https://www.nefe.org/news/2022/04/Insights-Financial-Capability-FINRA-NEFE.pdf

### 「拿铁因子」为什么失败
David Bach 的「每天 $5 咖啡 = 40 年后 $948,000」是最著名的金融数学时刻。但 Chicago Booth 研究发现：
- 光靠「震惊的大数字」不改变行为
- 人需要同时相信：未来的自己重要 + 这个数字和自己有关
- 🔗 https://www.chicagobooth.edu/review/how-to-get-yourself-skip-that-latte-save-money

### 真正有冲击力的数学时刻：意外的差值
人们实际上「以为自己订阅花了 $86/月，实际 $219/月」——**这个意外差值才是行为改变的触发器**，不是 40 年后的预测。

**应用到游戏设计**：不要展示遥远未来，要展示用户不知道自己已经处于的处境。

---

## 三、高忠诚度日常游戏的结构

### 数据：Streak 的威力
- 达到 7 天 streak 的用户，次日回归率提升 **2.4 倍**
- Duolingo 一次 streak 机制改动，让 7+ 天 streak 用户数增加 40%
- 🔗 https://blog.duolingo.com/how-duolingo-streak-builds-habit
- 🔗 https://blog.duolingo.com/improving-the-streak

### 高忠诚度产品的共同结构
（Wordle / NYT Spelling Bee / Connections / Duolingo 都一样）

| 要素 | 机制 |
|------|------|
| 单次时长 | 5-15 分钟，不能无限玩 |
| 每日硬重置 | 午夜消失，今天不做就没了 |
| 单一完成状态 | 「做完了」这个感觉必须清晰 |
| 可分享的结果 | 不剧透内容，但展示你的成就（Wordle 格子、streak 数字）|
| 明天的钩子 | 要么未完成（Spelling Bee 差一点到 Queen Bee），要么新内容重置 |

---

## 四、人一生必须学的金融数学（课程大纲）

按照「对生活决策的实际影响力」排序，不按学术难度：

### 第一层：基础认知（大多数人从未真正理解）
1. **复利** — 时间才是最重要的变量（72法则：钱翻倍需要 72÷年利率 年）
2. **通胀侵蚀** — 「存钱」本质上是在亏钱，购买力如何消失
3. **真实时薪** — 这个东西实际花了我多少小时命（税后工资÷真实工作时间）
4. **债务陷阱数学** — 信用卡最低还款的真实成本

### 第二层：决策数学（做对这几个决策，余生受益）
5. **机会成本** — 选A等于放弃什么，机会成本从不为零
6. **地理套利** — 同样的储蓄率在不同地方的威力差几十倍
7. **薪资谈判的终身影响** — 第一份工资低 ¥1000，30年后差多少？
8. **生活通胀陷阱** — 收入涨了，为什么存款没涨？

### 第三层：概率与风险（大多数人完全没有直觉）
9. **期望值** — 如何给不确定事件定价
10. **保险数学** — 什么情况下买保险是理性的
11. **税的数学** — 边际税率 vs 实际税率，为什么加薪不一定合算

### 第四层：系统思维（最难，也最值得）
12. **复利的极限** — 为什么Warren Buffett 95% 的财富在 65 岁以后才来
13. **收益率 vs 储蓄率** — 穷人更应该关注储蓄率，富人才应该关注收益率
14. **FIRE 数学** — Trinity Study 的 4% 法则，永续提取的条件

---

## 五、我们已有的 vs. 空缺

### 已有
- 复利（CompoundCalculator）
- FIRE / 4% 法则（CompoundCalculator + EscapeCalculator 数学课）
- 地理套利（EscapeCalculator）
- 债务（DebtCalculator）
- 期望值的雏形（PollGame）

### 空缺
- 通胀侵蚀（视觉化最有冲击力）
- 真实时薪（「这件事花了我多少小时命」）
- 机会成本
- 薪资谈判的终身影响
- 生活通胀陷阱
- 保险期望值
- 边际税率体感

### 最大的结构性空缺
现有工具是**工具**，不是**游戏**。缺的不是数学内容：
- 没有**角色/进度**（你是谁，你在哪个阶段）
- 没有**今天的任务**（每日单次完整体验）
- 没有**明天再来的理由**（streak、悬念、社区胜率）

---

## 六、延伸阅读

### 游戏化设计
- 🔗 Octalysis 游戏化框架（Yu-kai Chou）: https://yukaichou.com/gamification-examples/octalysis-complete-gamification-framework/
- 🔗 Nir Eyal《Hooked》钩子模型（触发→行动→奖励→投入）

### 金融数学教育研究
- 🔗 NEFE 财务教育效果研究索引: https://www.nefe.org/research/
- 🔗 行为经济学与金融决策（Kahneman）：《Thinking, Fast and Slow》第5部分

### 值得玩的参考产品
- 🔗 Spent（贫困模拟游戏）: https://playspent.org/ — 在压力下做决策，感受穷人的数学
- 🔗 Budget Challenge（学生版）: https://budgetchallenge.com/
- 🔗 Financial Football（NFL+Visa）: 用美式足球场景学金融
- 🔗 Sortify（NYT，分类游戏）: https://www.nytimes.com/games — 研究单次体验设计

### 关于 Streak 和习惯
- 🔗 BJ Fogg《Tiny Habits》— 习惯设计，比 James Clear《Atomic Habits》更适合 app 设计
- 🔗 Duolingo 公开的增长案例: https://blog.duolingo.com/category/learning/

---

*下一步：读游戏设计文档（git 后），对照课程大纲找空缺和切入点*
