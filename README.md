# 商学院赛车策略仿真实验室

面向商学院教学的赛车策略模拟平台。学生通过制定驾驶策略（加速、刹车、转向），利用后端封装的物理引擎，在广东国际赛车场模型上进行仿真测试。

**赛道**: 广东国际赛车场 (GIC) 2820m | **版本**: v5.0

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + TailwindCSS + Vite |
| 后端 | Python FastAPI + SQLite + Redis |
| 物理引擎 | RacingTJ_GDi_circle_4test.py（外部依赖，需单独获取） |

---

## 系统要求

- Python 3.9+
- Node.js 18+
- Redis（本地或 Docker）
- RAM 4GB+

---

## 部署步骤

### 1. 克隆仓库

```bash
git clone https://github.com/halfmoon82/racing-sim.git
cd racing-sim
```

### 2. 配置物理引擎

物理引擎文件 `RacingTJ_GDi_circle_4test.py` 需单独获取，并放置到对应路径。
默认路径在 `backend/main.py` 中配置：

```python
PHYSICS_ENGINE_PATH = Path.home() / "Desktop/AI创新" / "RacingTJ_GDi_circle_4test.py"
```

根据实际路径修改该变量后再启动后端。

### 3. 安装后端依赖

```bash
cd backend
pip install fastapi uvicorn sqlalchemy redis pandas numpy
```

推荐使用虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install fastapi uvicorn sqlalchemy redis pandas numpy
```

### 4. 启动 Redis

```bash
# macOS (Homebrew)
brew install redis
redis-server --daemonize yes

# Linux
sudo apt install redis-server
sudo systemctl start redis

# Docker（任意平台）
docker run -d -p 6379:6379 redis:latest
```

验证：`redis-cli ping` 返回 `PONG` 即可。

### 5. 初始化数据库

```bash
cd backend
python3 -c "from main import init_db; init_db()"
```

数据库文件生成在 `database/racing_sim.db`。

### 6. 设置 Admin 密码

```bash
python3 << 'EOF'
import sqlite3, hashlib
pwd = input("设置 Admin 密码: ")
h = hashlib.sha256(pwd.encode()).hexdigest()
conn = sqlite3.connect('../database/racing_sim.db')
conn.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (h,))
conn.commit()
conn.close()
print("Admin 密码已设置")
EOF
```

或直接使用一键部署脚本（步骤 3–6 自动完成）：

```bash
chmod +x deploy.sh
./deploy.sh
```

### 7. 配置前端环境变量

```bash
cp frontend/.env.example frontend/.env   # 如有示例文件
# 或手动创建
cat > frontend/.env << 'EOF'
VITE_API_BASE_URL=http://localhost:8000
EOF
```

### 8. 安装前端依赖

```bash
cd frontend
npm install
```

### 9. 启动服务

**开发模式（两个终端）：**

```bash
# 终端 1 — 后端
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 终端 2 — 前端
cd frontend
npm run dev
```

**一键启动脚本（后台运行）：**

```bash
chmod +x start.sh
./start.sh
# 日志: tail -f /tmp/racing_backend.log
#       tail -f /tmp/racing_frontend.log
```

访问地址：
- 前端：http://localhost:3000
- 后端 API 文档：http://localhost:8000/docs

---

## 生产部署

### 前端构建

```bash
cd frontend
npm run build
# 产物在 frontend/dist/，部署到任意静态服务器或 Nginx
```

### 后端生产启动

```bash
pip install gunicorn
cd backend
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

或使用 PM2（见 `ecosystem.config.js`）：

```bash
pm2 start ecosystem.config.js
```

### Nginx 配置参考

```nginx
server {
    listen 80;
    server_name your-domain.com;

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

详细生产部署说明见 [DEPLOY.md](./DEPLOY.md)。

---

## 默认账号

| 角色 | 用户名 | 说明 |
|------|--------|------|
| Admin | `admin` | 部署时手动设置密码，仅限本地访问 |
| Teacher | 由 Admin 创建 | 最多 4 个终端同时登录 |
| Student | `Student_01`~`Student_10` | 由 Teacher 生成密码，首入原则单终端 |

---

## 项目结构

```
racing-sim/
├── backend/
│   └── main.py              # FastAPI 主应用（含物理引擎调用）
├── frontend/
│   ├── src/
│   │   ├── pages/           # LoginPage, StudentDashboard, TeacherDashboard, AdminPanel
│   │   ├── components/      # 共享组件（GlobalCommand, PasswordResetModal 等）
│   │   └── contexts/        # AuthContext
│   └── vite.config.ts
├── database/
│   └── schema.sql           # SQLite 表结构
├── uat/                     # UAT 测试脚本与策略样本
├── scripts/                 # 并发/冒烟测试脚本
├── deploy.sh                # 一键初始化部署脚本
├── start.sh                 # 一键启动脚本
├── ecosystem.config.js      # PM2 配置
└── DEPLOY.md                # 完整生产部署指南
```

---

## CSV 策略格式

```csv
now_pos,strategy,turn_id,steer_L/R,steer_degree
0,a,0,0,0
300,c,turn1,L,45
...
```

- **弯道序列**：turn1 → turn2 → turn4 → turn6 → turn7 → turn8 → turn10 → turn12 → turn13（共 9 个）
- 非弯道行 `turn_id` / `steer_L/R` 用 `0` 占位，前端提交时自动清洗
- `strategy` 值：`a` / `b` / `c`（不区分大小写，前端自动转小写）

---

## 故障排查

**物理引擎导入失败**：检查 `PHYSICS_ENGINE_PATH` 路径，确认文件存在且 `pandas`/`numpy` 已安装。

**Redis 连接失败**：运行 `redis-cli ping`，确认 Redis 正在监听 6379 端口。

**端口冲突**：
- 后端换端口：`uvicorn main:app --port 8080`
- 前端换端口：修改 `vite.config.ts` 中的 `server.port`

**CSV 提交报错"缺少转向方向"**：检查非弯道行是否使用了非 `0` 的占位符，或升级到最新前端代码（已修复自动清洗逻辑）。

---

## License

Internal Use Only — Business School Racing Simulation Project
