# 预言家日报 · Design System

视觉源头：claude.ai/design（导出 bundle 在 `design/` 目录）
实现原则：现有 Flask 结构不动，逐层叠加预言家日报美学。

---

## 标语

**Masthead 副标（短版）**
> 时间魔法，点石成金

**完整版**（About 页 / 首次登录欢迎语）
> 对所有魔法来说，时间魔法都是入门课。在此之前，十年是我们献给魔法龙的贡品——无论你想学变形，还是点石成金。

---

## DS-01 封蜡印章（Wax Seal）

**范围**：watchlist 卡片、首页持仓区、股票详情页评级
**原则**：只改视觉，不改信息层级

- Watchlist / 首页：grade-tag 替换为封蜡圆形背景（28-32px）
- 详情页：评级旁加 24px 印章作装饰子结构，数字仍为主角，印章为底
- 颜色方案：A=绿(#2d5a27) / B=金(#b8952a) / C=灰(#8a7560) / D=红(#8b0000)

**状态**：待实现

---

## DS-02 MagicRule（魔法分割线）

**范围**：首页、brief 页的 section 分割线
**原则**：只改视觉，CSS class 替换，不动信息结构

- `style.css` 加 `.magic-rule` class：金色渐变 + 闪烁动效
- 替换现有 `<hr class="section-rule">` → `<hr class="magic-rule">`

**状态**：待实现

---

## DS-03 Masthead 副标题

**范围**：`base.html` masthead
- 品牌名下方加 12px 斜体副标：「时间魔法，点石成金」
- 右侧加「第 X 期」期刊编号（按注册天数或固定递增）

**状态**：待实现

---

## DS-04 首页「今日预言」入口卡（第4张）

**范围**：`index.html` home-cards-row
- 新增第4张卡，不替换「今日简报」
- 样式：✒ 图标 + 报纸叙事文案 + 羊皮纸背景处理
- 点击进入预言流程（DS-07 实现后接路由，现在先占位）

**状态**：待实现

---

## DS-05 市场信号重组

**范围**：`index.html` + `style.css`
**决定**：删除 pulse bar，市场数字下沉进内容区

- 删除 `{% block pulse_bar %}` 及相关逻辑（`has_stocks` 判断一并移除）
- 首页右侧新闻栏顶部加「市场信号」板块：
  - 恐贪指数 / USD/CNY / 上证综指 / NZX 50 四行紧凑数据
  - 羊皮纸背景（`background: #faf0d8; border: 1px solid #c4b89a`）
- 数据来源不变，仍从 `market` context 读取

**状态**：待实现

---

## DS-06 知识专栏 Clipping 卡片

**范围**：`index.html` 底部新增区域
- 先静态硬编码三张：复利 / 护城河 / 宏观感知
- 复利卡点击展开计算器（纯前端 JS，无后端需求）
- 未解锁的卡显示为灰暗状态

**状态**：待实现

---

## DS-07 预言系统（后端，最后做）

- DB 新表 `predictions`（user_id, stock_code, direction, reason, created_at, resolved）
- `/quest` 路由 + 4步流程页
- Groq 从现有 analysis 数据生成三条线索
- 7天后自动揭晓结果，展示「更正声明」复盘页

**状态**：规划中，待 DS-01 至 DS-06 完成后启动

---

## 执行顺序

```
DS-01 封蜡印章
DS-02 MagicRule
DS-03 Masthead 副标
DS-04 今日预言入口卡
DS-05 市场信号重组
DS-06 知识专栏
DS-07 预言系统（后端）
```
