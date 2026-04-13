#!/bin/bash

echo "🔄 重启 Flask 应用..."

# 杀死旧的进程
echo "1️⃣ 杀死旧的 Flask 进程..."
pkill -f "app.py" 2>/dev/null || true
echo "   ✓ 旧进程已杀死"

# 等待进程完全退出
sleep 2

# 启动新的
echo ""
echo "2️⃣ 启动新的 Flask 应用..."
cd /Users/poluovoila/.claude/skills/stock-radar
nohup /opt/homebrew/bin/python3 app.py >> /tmp/flask-radar.log 2>&1 &

sleep 2

# 检查是否启动成功
if lsof -i :5002 >/dev/null 2>&1; then
    echo "   ✓ Flask 应用已启动 (端口 5002)"
    echo ""
    echo "3️⃣ 验证应用..."

    # 测试一个请求
    python3 debug_fundamentals.py

    echo ""
    echo "✅ 完成！"
    echo ""
    echo "现在你可以："
    echo "  1. 打开浏览器访问 http://localhost:5002"
    echo "  2. 搜索 INTC 或其他非A股"
    echo "  3. 点击'价值档案'标签 → 应该能看到完整的财务指标"
else
    echo "   ❌ Flask 应用启动失败，请检查端口"
    echo "   运行: lsof -i :5002"
fi
