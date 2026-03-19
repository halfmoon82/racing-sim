#!/bin/bash
# 商学院赛车策略仿真实验室 - 启动脚本

echo "🏁 商学院赛车策略仿真实验室"
echo "=============================="

# 检查 Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo "🔄 启动 Redis..."
    redis-server --daemonize yes
    sleep 1
fi

if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis 运行中"
else
    echo "❌ Redis 启动失败"
    exit 1
fi

# 启动后端
echo "🚀 启动后端服务 (端口 8000)..."
nohup python3 -c "
import uvicorn
import sys
sys.path.insert(0, '/Users/macmini/.openclaw/workspace/racing-sim/backend')
from main import app
uvicorn.run(app, host='0.0.0.0', port=8000)
" > /tmp/racing_backend.log 2>&1 &

sleep 2

# 检查后端
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✅ 后端服务运行中 (http://localhost:8000)"
else
    echo "⚠️ 后端启动中，请稍后检查..."
fi

# 启动前端
echo "🎨 启动前端服务 (端口 3000)..."
cd /Users/macmini/.openclaw/workspace/racing-sim/frontend
npm run dev > /tmp/racing_frontend.log 2>&1 &

echo ""
echo "=============================="
echo "服务启动完成!"
echo ""
echo "📱 访问地址:"
echo "  前端: http://localhost:3000"
echo "  后端: http://localhost:8000"
echo "  API文档: http://localhost:8000/docs"
echo ""
echo "👤 默认账号:"
echo "  Admin: admin / admin123"
echo ""
echo "📊 查看日志:"
echo "  后端: tail -f /tmp/racing_backend.log"
echo "  前端: tail -f /tmp/racing_frontend.log"
