# SirenBuffet 前端框架文档

> 每次前端会话开始前读这个文件。

---

## 定位

**公开层**：任何人都能访问的金融教育工具站，无需登录。
**私人层**（Flask 后端）：登录用户的股票分析，数据来自 `NEXT_PUBLIC_API_URL`（本地 5001，生产 Fly.io）。

核心哲学：知识本身的力量——最普通的人也能获益，不要求变成人上人。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 框架 | Next.js 15 App Router |
| 样式 | Tailwind CSS |
| 数据库 | Prisma 5 + SQLite（本地 `prisma/dev.db`） |
| 认证 | Auth.js v5 (next-auth@beta) + PrismaAdapter + Google OAuth |
| 数据持久化 | Server Actions (`src/app/actions/plan.ts`) |

---

## 页面结构

```
/                     首页「预言家日报」（公开）
  └─ PollGame          今日预言投票（涨/跌，7天后见分晓）
  └─ CompoundMini      复利小游戏入口卡片

/blog/[code]          股票分析详情（公开，读 Flask API）

/tools/compound       复利 / FIRE 计算器（全功能）
/tools/escape         出逃路线计算器
/tools/debt           负债计算器

/login                登录
/register             注册
/forgot-password      忘记密码
/reset-password       重置密码
```

---

## 组件目录

### `PollGame`
今日预言投票。读 `/api/public/poll/today`，投票 POST `/api/public/poll/vote`。
- 显示三条线索，押注涨/跌
- 投票后显示进度条（多少人押涨/跌）
- 7天后显示结果（outcome 字段）
- 防重复投票（后端 400 响应）

### `CompoundCalculator`
全功能复利 / FIRE 计算器。完全客户端，无需登录。
- **游戏化评分 UI**：City Journey Bar → FIRE Years 英雄区 → Rate 预设 → Core Controls → Advanced 折叠 → Chart
- 城市生活成本通过 `useCityData` hook 从 Flask 拉取（`/api/public/city-data`）
- `CityPicker` 组件：城市按 tier 分组，颜色区分

### `EscapeCalculator`
出逃路线：在哪挣，去哪躺。完全客户端。
- **工作城市**（8个，分三档）：存本地货币原始数据，通过 `FX` 汇率对象自动换算 CNY
  - 更新汇率：改 `FX` 对象一行，所有城市自动重算
  - 更新最低工资：改对应城市的 `salaryLocal`
- **退休城市**（12个）：月消费参考
- **数学课区块**：拆解积累期复利 + 停工后 4% 法则永续提取
- **上海对比**：¥1,500/月（诚实估算，拼命省也就这样）
- 汇率核对日期显示在页脚

### `CompoundMini`
首页嵌入的迷你复利器。带城市参考和 CTA "算算你还有多少年不用打工喵 →"

### `DebtCalculator`
负债计算器。（功能待补充文档）

### `Navbar`
顶部导航。工具入口 + 登录状态。

### `AuthCard`
登录/注册卡片，复用于多个 auth 页面。

---

## 数据流

```
首页/blog           → Flask API（公开端点，SSR fetch，revalidate 3600s）
PollGame 投票       → Flask API（POST，client-side）
useCityData hook    → Flask API（/api/public/city-data，client-side）
LifePlan 存取       → Server Action → Prisma → SQLite（本地 dev.db）
工具计算器          → 纯客户端，无网络请求
```

---

## 已完成的游戏化元素

| 元素 | 位置 | 机制 |
|------|------|------|
| 今日预言投票 | 首页 PollGame | 押注涨/跌 → 7天验证 → 社区胜率可见 |
| FIRE 倒计时 | CompoundCalculator | 大字英雄数字 + 实时联动滑块 |
| 出逃路线 | EscapeCalculator | 选地图 → 看存钱速度 → 数学课拆解 |
| 数学课区块 | EscapeCalculator | 积累期 vs 停工后分开展示，数字实时更新 |

---

## 待做 / 下一步

- `/tools/plan`：多阶段人生规划器（数据模型已在 Prisma schema：`LifePlan.phases`）
- Google OAuth 还未填入真实 credentials（`.env.local` 中为空）
- `last_login` 未记录（users 表有字段但没有写入逻辑）
- 前端尚未部署（目前只有本地 dev server）
