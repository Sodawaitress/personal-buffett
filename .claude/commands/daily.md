从 GitHub 拉取最新的 Routine 改进日志，展示最近的分析和预言验证结果，然后和用户一起讨论需要改进的地方。

步骤：
1. 用 WebFetch 读取 `https://raw.githubusercontent.com/Sodawaitress/personal-buffett/main/knowledge/improvement_log.md`
2. 找出最新的「今日五选」和「验证」条目（文件末尾部分）
3. 展示给用户：今天选了哪五只、预言是什么、上次预言验证结果如何
4. 问用户：「有没有需要改的地方？还是聊聊这次分析？」

如果文件不存在（404），说明 Routine 还没跑过，提示用户手动触发一次 Routine。
