# Stock Radar - 搜索功能修改 Code Review Checklist

⚠️ **IMPORTANT**: 搜索功能代码重复在两个文件中（index.html 和 watchlist.html）
修改搜索代码时必须使用这个 Checklist，防止变量混淆 bug。

## 修改搜索代码前的检查

```
修改内容: ___________________________________
修改人: ___________________________________
修改日期: ___________________________________
```

### 1️⃣ 识别修改范围

- [ ] 我要修改的搜索代码位于哪个文件？
  - [ ] index.html (第 237-279 行)
  - [ ] watchlist.html (第 649-683 行)  
  - [ ] 两个都要改
  - [ ] static/search.js（如果已提取）

- [ ] 这个修改是否会影响其他文件？
  - [ ] 是 → 检查所有受影响的地方
  - [ ] 否 → 继续

### 2️⃣ 变量一致性检查 ⭐ 最重要

这是防止 watchlist.html bug 再发生的关键！

**规则**: doSearch() 接收的变量必须在整个函数中保持一致

- [ ] **第一行检查**: 检查 API 响应的变量赋值
  ```javascript
  const items = await (await fetch(...)).json();
  // 或
  const data = await resp.json();
  ```
  我的代码使用的是: ________________ (items 或 data)

- [ ] **第二行检查**: 检查加载状态判断
  ```javascript
  if (data && data.loading) { ... }    // ✓ 正确（如果是 data）
  if (items && items.loading) { ... }  // ✓ 正确（如果是 items）
  if (data && data.loading) { ... }    // ❌ 错误（如果接收的是 items）
  ```
  我的代码使用的是: ________________ (必须与第一步一致!)

- [ ] **第三行检查**: 检查数组操作
  ```javascript
  const results = Array.isArray(items) ? items : [];  // ✓ 一致
  const results = Array.isArray(data) ? data : [];    // ✓ 一致
  const results = Array.isArray(items) ? data : [];   // ❌ 不一致!
  ```
  我的代码使用的是: ________________

- [ ] ✅ 前后一致性验证通过

### 3️⃣ 文件一致性检查

**规则**: 如果两个文件有相同的搜索代码，修改一个就要修改另一个

- [ ] 检查 index.html 的搜索代码是否需要同样的修改？
  - [ ] 是 → 我将同时修改 index.html
  - [ ] 否 → 记录原因: _________________

- [ ] 检查 watchlist.html 的搜索代码是否需要同样的修改？
  - [ ] 是 → 我将同时修改 watchlist.html
  - [ ] 否 → 记录原因: _________________

- [ ] ✅ 所有副本已更新或记录了原因

### 4️⃣ 代码质量检查

- [ ] 代码中是否有 console.error 或日志记录？
  - [ ] 是 → 检查是否清理了开发代码
  - [ ] 否 → 继续

- [ ] 是否使用了未定义的变量或拼写错误？
  - [ ] 否 → 继续
  - [ ] 是 → 修复它们

- [ ] 是否添加了足够的注释，说明这是重复代码？
  ```javascript
  // ⚠️ IMPORTANT: 这个函数在 index.html 和 watchlist.html 中重复
  // 修改此处时必须同步更新另一个文件！
  ```
  - [ ] 是 → 良好实践！

### 5️⃣ 自动化测试

运行测试来验证修改：

```bash
cd /Users/poluovoila/.claude/skills/stock-radar
python3 tests/test_search.py
```

- [ ] 所有测试都通过了吗？
  - [ ] ✅ 通过 → 继续
  - [ ] ❌ 失败 → 检查错误信息并修复

### 6️⃣ 手工测试（关键！）

在浏览器中实际测试搜索功能：

#### index.html 首页搜索测试
- [ ] 搜索 "AAPL" → 应该显示下拉列表和搜索结果
- [ ] 搜索 "茅台" → 应该显示下拉列表和搜索结果
- [ ] 搜索 "invalid_xyz" → 应该显示"没有找到结果"

#### watchlist.html 搜索测试
- [ ] 打开 watchlist 页面
- [ ] 点击 "Add to Watchlist" 的搜索框
- [ ] 搜索 "AAPL" → 应该显示下拉列表
- [ ] 搜索 "茅台" → 应该显示下拉列表
- [ ] 搜索 "invalid_xyz" → 应该显示"没有找到结果"

#### 清除缓存后重新测试
- [ ] 按 Cmd+Shift+R（Mac）或 Ctrl+Shift+F5（Windows）强制刷新
- [ ] 重新进行上述测试 → 结果应该相同

- [ ] ✅ 所有手工测试通过

### 7️⃣ 浏览器兼容性（如果需要）

- [ ] Chrome 上测试 → ✓
- [ ] Firefox 上测试 → ✓
- [ ] Safari 上测试 → ✓（Mac 用户）

### 8️⃣ 最终检查清单

在提交之前：

- [ ] 所有文件都保存了吗？
- [ ] 自动化测试都通过了吗？
- [ ] 手工测试都通过了吗？
- [ ] 我检查了所有需要同步修改的地方吗？
- [ ] 代码中有注释说明这是重复代码吗？
- [ ] 没有遗留的 console.log 或调试代码吗？

## ✅ 修改完成

修改者签名: ___________________________  
日期: ___________________________

通过所有检查 ✓ 可以提交/部署

---

## 📝 常见问题

### Q: 为什么要检查两个文件？
A: 因为搜索功能的代码在 index.html 和 watchlist.html 中重复了。这次 bug 就是因为其中一个文件用错了变量名。最终我们应该提取到 static/search.js 来一次性解决。

### Q: 我修改了一个文件但忘记改另一个怎么办？
A: 运行 `python3 tests/test_search.py` 会检测到变量不一致。

### Q: 什么时候应该使用这个 Checklist？
A: 每次修改搜索代码时。复制粘贴这个清单并填写。

### Q: 如果我只是改 CSS 或样式需要用这个吗？
A: 不需要，这个清单只适用于修改 JavaScript 逻辑。

---

## 🎯 下一步优化

这个 Checklist 是临时方案。长期应该：

1. 【优先级 1】创建 static/search.js（1-2小时工作量）
   - 一份代码，所有地方共用
   - 从根本上避免重复 bug

2. 【优先级 2】集成到 CI/CD
   - 自动运行 tests/test_search.py
   - 变量不一致时自动拒绝提交

参考: `/tmp/防退化方案.md` 中的完整实施方案
