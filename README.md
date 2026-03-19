# 商学院赛车策略仿真实验室 (Racing Strategy Simulation Lab)

## 项目概述

面向商学院教学的赛车策略模拟平台。学生通过制定驾驶策略（加速、刹车、转向），利用后端封装的物理引擎，在广东国际赛车场模型上进行仿真测试。

**赛道**: 广东国际赛车场 (GIC) 2820m  
**版本**: v5.0 Final Release  
**开发日期**: 2026-02-14

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + TailwindCSS |
| 后端 | Python FastAPI + SQLite + Redis |
| 物理引擎 | RacingTJ_GDi_circle_4test.py (封装为黑盒) |
| 部署 | OpenClaw / Docker |

---

## 核心功能

### 1. 用户角色
- **Admin**: 本地访问，管理Teacher账号，全局重置
- **Teacher**: 最多4终端登录，控制轮次，管理学生，监控状态
- **Student**: 首入原则单终端登录，受轮次和次数约束

### 2. 物理引擎集成
- 输入CSV格式策略数据
- 运行5次取最优（因random.random()波动）
- 表头严格匹配: now_pos, strategy, turn_id, steer_L/R, steer_degree
- 弯道序列: turn1→2→4→6→7→8→10→12→13（跳过3,5,9,11）

### 3. 并发控制
- Job UUID隔离工作目录 /tmp/racing_sim/{job_id}/
- 提交配额锁: 事务保护检查轮次状态+次数限制

---

## 快速启动

```bash
# 1. 启动 Redis
redis-server --daemonize yes

# 2. 启动后端
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 3. 启动前端
cd frontend
npm run dev
```

访问 http://localhost:3000

---

## 项目结构

```
racing-sim/
├── backend/
│   └── main.py              # FastAPI 主应用
├── frontend/
│   ├── src/
│   │   ├── pages/           # Login, Student, Teacher, Admin
│   │   ├── components/      # 共享组件
│   │   └── contexts/        # AuthContext
│   └── package.json
├── database/
│   └── schema.sql           # SQLite 数据库结构
├── deploy.sh                # 一键部署脚本
├── DEPLOY.md                # 部署指南
└── openclaw.yaml            # OpenClaw 部署配置
```

---

## 默认账号

| 角色 | 用户名 | 密码 | 说明 |
|------|--------|------|------|
| Admin | admin | 需初始化 | 仅限本地访问 |
| Teacher | 由Admin创建 | - | 最多4终端 |
| Student | Student_01~10 | 由Teacher生成 | 首入原则 |

---

## 物理引擎参数

- **赛道长度**: 2820m
- **理论最佳圈速**: 67.07s
- **车辆质量**: 600kg
- **最高速度**: 300km/h (83.33m/s)

---

## 开发团队

- **需求分析**: Codex (GPT-5.3-codex)
- **后端开发**: Codex (GPT-5.3-codex)
- **前端开发**: Codex (GPT-5.3-codex)
- **部署配置**: DeepEye

---

## License

Internal Use Only - Business School Racing Simulation Project
