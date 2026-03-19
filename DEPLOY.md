# 商学院赛车策略仿真实验室 - 部署指南

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React Frontend │────▶│  FastAPI Backend│────▶│   SQLite DB     │
│   (Port 3000)   │     │   (Port 8000)   │     │  (racing_sim.db)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Redis Server   │
                        │   (Port 6379)   │
                        └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Physics Engine │
                        │ RacingTJ_*.py   │
                        └─────────────────┘
```

## 快速启动

### 1. 安装依赖

```bash
# 后端依赖
pip install fastapi uvicorn sqlalchemy redis pandas numpy

# 前端依赖
cd frontend
npm install
```

### 2. 启动 Redis

```bash
# macOS
brew install redis
redis-server --daemonize yes

# 或 Docker
docker run -d -p 6379:6379 redis:latest
```

### 3. 初始化数据库

```bash
cd backend
python -c "from main import init_db; init_db()"
```

### 4. 启动后端

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 启动前端

```bash
cd frontend
npm run dev
```

访问 http://localhost:3000

---

## 生产部署

### 使用 Gunicorn + Nginx

```bash
# 安装生产依赖
pip install gunicorn

# 后端生产启动
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000

# 前端构建
cd frontend
npm run build
# 将 dist/ 目录部署到 Nginx
```

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name calc.socialmore.cn;

    location / {
        root /path/to/racing-sim/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 默认账号

### Admin (本地访问)
- Username: `admin`
- Password: 需要在数据库初始化后手动设置

### 初始化 Admin 密码

```bash
cd backend
python3 << 'EOF'
import sqlite3
import hashlib

def hash_password(pwd):
    import hashlib
    return hashlib.sha256(pwd.encode()).hexdigest()

conn = sqlite3.connect('../database/racing_sim.db')
cursor = conn.cursor()
cursor.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", 
               (hash_password('your_admin_password'),))
conn.commit()
conn.close()
print("Admin password updated")
EOF
```

---

## 系统要求

- **OS**: macOS 12+ / Linux / Windows WSL
- **Python**: 3.9+
- **Node.js**: 18+
- **RAM**: 4GB+
- **Disk**: 1GB+

---

## 物理引擎路径配置

确保 `RacingTJ_GDi_circle_4test.py` 在正确位置：

```python
# backend/main.py 中配置
PHYSICS_ENGINE_PATH = Path.home() / "Desktop/AI创新" / "RacingTJ_GDi_circle_4test.py"
```

---

## 故障排查

**Q: 物理引擎导入失败**
- 检查文件路径是否正确
- 确保 pandas, numpy 已安装

**Q: Redis 连接失败**
- 检查 Redis 是否运行: `redis-cli ping`
- 默认端口 6379 是否被占用

**Q: 端口冲突**
- 修改 backend port: `uvicorn main:app --port 8080`
- 修改 frontend port: 在 vite.config.ts 中设置

---

## 备份

定期备份以下文件：
- `database/racing_sim.db` - 数据库
- `~/.cloudflared/` - 隧道配置（如使用 Cloudflare）
