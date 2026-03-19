#!/bin/bash
# 一键部署脚本

set -e

echo "🚀 商学院赛车策略仿真实验室 - 部署脚本"
echo "=========================================="

# 检查环境
echo "📋 检查环境..."
python3 --version || { echo "❌ Python3 未安装"; exit 1; }
node --version || { echo "❌ Node.js 未安装"; exit 1; }

# 安装后端依赖
echo "📦 安装后端依赖..."
pip3 install fastapi uvicorn sqlalchemy redis pandas numpy -q

# 检查 Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️ Redis 未运行，尝试启动..."
    redis-server --daemonize yes || { echo "❌ Redis 启动失败"; exit 1; }
    sleep 2
fi
echo "✅ Redis 运行正常"

# 初始化数据库
echo "🗄️ 初始化数据库..."
cd backend
python3 -c "from main import init_db; init_db()"
echo "✅ 数据库初始化完成"

# 设置 Admin 密码
read -sp "设置 Admin 密码: " ADMIN_PASS
echo
python3 << EOF
import sqlite3
import hashlib
import sys

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

try:
    conn = sqlite3.connect('../database/racing_sim.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", 
                   (hash_password('$ADMIN_PASS'),))
    conn.commit()
    conn.close()
    print("✅ Admin 密码已设置")
except Exception as e:
    print(f"❌ 设置失败: {e}")
    sys.exit(1)
EOF

# 安装前端依赖
echo "📦 安装前端依赖..."
cd ../frontend
npm install

echo ""
echo "✅ 部署完成！"
echo ""
echo "启动命令:"
echo "  终端1: cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo "  终端2: cd frontend && npm run dev"
echo ""
echo "访问地址:"
echo "  前端: http://localhost:3000"
echo "  后端: http://localhost:8000"
echo "  API文档: http://localhost:8000/docs"
