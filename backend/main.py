# 商学院赛车策略仿真实验室 - 后端
# FastAPI Application

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, UploadFile, File, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse
from fastapi import WebSocket
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import sqlite3
import redis
import hashlib
import uuid
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import threading

# ==========================================
# 日志配置（Fix 7: 结构化日志）
# ==========================================
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("racing-sim")

# 添加到路径以导入物理引擎
sys.path.insert(0, str(Path.home() / "Desktop/AI创新"))

# ==========================================
# 配置
# ==========================================
DATABASE_PATH = Path(__file__).parent.parent / "database" / "racing_sim.db"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
PHYSICS_ENGINE_PATH = Path.home() / "Desktop/AI创新" / "RacingTJ_GDi_circle_4test.py"
TEMP_WORK_DIR = Path("/tmp/racing_sim")
MAX_STUDENT_SESSIONS = 1  # 学生首入原则
MAX_TEACHER_SESSIONS = 4  # 教师最多4终端
HISTORY_LIMIT = 30  # FIFO历史记录上限

# Physics engine (and its pandas monkeypatch) is not thread-safe.
# Serialize simulation to provide queue-like behavior and avoid 500s under concurrent submissions.
SIMULATION_LOCK = threading.Lock()

# Fix 3: 仿真队列深度保护
_sim_queue = 0
_sim_queue_lock = threading.Lock()
MAX_SIM_QUEUE = 3  # 1 运行中 + 2 等待，适合 20 用户规模

# ==========================================
# 数据库连接
# ==========================================
def get_db():
    # FastAPI sync endpoints may run dependencies in a threadpool; allow SQLite connection across threads.
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Fix 1: WAL 模式 + busy_timeout（读写不互相阻塞，等待 10s 而非立即报错）
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """初始化数据库"""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH))
    # Fix 1: 持久化 WAL 模式（数据库文件级别，重启后保持）
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.commit()
    with open(Path(__file__).parent.parent / "database" / "schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.close()
    logger.info("database initialized: journal_mode=WAL")

# ==========================================
# Redis连接
# ==========================================
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# ==========================================
# 认证与安全
# ==========================================
security = HTTPBearer()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def create_session_token() -> str:
    return f"sess_{uuid.uuid4().hex}"

def create_job_id(user_id: int) -> str:
    return f"job_{uuid.uuid4().hex}_{user_id}"

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)):
    token = credentials.credentials
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.*, u.username, u.role, u.display_name 
        FROM sessions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.session_token = ? AND s.is_active = 1 AND s.expires_at > datetime('now')
    """, (token,))
    session = cursor.fetchone()
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "session_id": session["id"],
        "user_id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
        "display_name": session["display_name"],
        "token": token
    }

def require_role(allowed_roles: List[str]):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# Admin 本地访问检查 - 允许已认证用户
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "::1", "192.168.50.160", "198.18.0.0/16", "155.254.105.0/24"]

async def check_localhost(request: Request):
    # 允许本地、Cloudflare隧道和Cloudflare边缘IP
    client_host = request.client.host
    if client_host in ALLOWED_HOSTS:
        return
    if client_host.startswith("198.18."):
        return
    if client_host.startswith("155.254."):
        return
    raise HTTPException(status_code=403, detail="Admin access restricted")

# ==========================================
# Pydantic 模型
# ==========================================
class LoginRequest(BaseModel):
    username: str
    password: str

class CreateTeacherRequest(BaseModel):
    username: str
    password: str
    display_name: str

class CreateRoundRequest(BaseModel):
    name: str
    max_attempts: int = Field(default=5, ge=1, le=20)
    auto_end_minutes: Optional[int] = None

class StrategySegment(BaseModel):
    now_pos: float = Field(..., ge=0, le=2820)
    strategy: str = Field(..., pattern="^[abc]$")  # a=加速, b=刹车, c=滑行
    is_corner: bool = False
    turn_id: Optional[str] = None
    steer_LR: Optional[str] = Field(None, pattern="^[LR]$")
    steer_degree: Optional[float] = Field(None, ge=0, le=360)
    
    @validator('turn_id')
    def validate_turn_id(cls, v, values):
        if values.get('is_corner') and v:
            # 禁止的弯道
            forbidden = ['turn3', 'turn5', 'turn9', 'turn11']
            if v in forbidden:
                raise ValueError(f"Turn {v} is not a corner (straight section)")
            # 允许的弯道
            allowed = ['turn1', 'turn2', 'turn4', 'turn6', 'turn7', 'turn8', 'turn10', 'turn12', 'turn13']
            if v not in allowed:
                raise ValueError(f"Invalid turn_id: {v}")
        return v

class SubmitStrategyRequest(BaseModel):
    segments: List[StrategySegment] = Field(..., min_items=9, max_items=50)

class ResetSystemRequest(BaseModel):
    confirmation: str = Field(..., pattern="^CONFIRM RESET$")

# ==========================================
# 业务逻辑
# ==========================================

class SubmissionGuard:
    """提交配额锁 - 防止并发突破限制"""
    
    @staticmethod
    def check_and_lock(user_id: int, round_id: int, max_attempts: int, db) -> int:
        """检查并分配尝试次数，返回当前尝试序号"""
        cursor = db.cursor()
        
        # 事务开始
        cursor.execute("BEGIN IMMEDIATE")
        try:
            # 检查轮次是否活跃
            cursor.execute("SELECT is_active FROM rounds WHERE id = ?", (round_id,))
            round_status = cursor.fetchone()
            if not round_status or not round_status["is_active"]:
                raise HTTPException(status_code=403, detail="Session Closed / 通道已关闭")
            
            # 检查已用次数
            cursor.execute("""
                SELECT COUNT(*) as count FROM records 
                WHERE user_id = ? AND round_id = ?
            """, (user_id, round_id))
            used = cursor.fetchone()["count"]
            
            if used >= max_attempts:
                raise HTTPException(status_code=403, detail="Out of Laps / 配额耗尽")
            
            attempt_number = used + 1
            db.commit()
            return attempt_number
            
        except Exception as e:
            db.rollback()
            raise e

def enforce_history_limit(user_id: int, db):
    """FIFO 30条 + Golden Record保护"""
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, result_time, is_dnf, created_at
        FROM records
        WHERE user_id = ?
        ORDER BY datetime(created_at) ASC, id ASC
    """, (user_id,))
    rows = cursor.fetchall()
    if len(rows) <= HISTORY_LIMIT:
        return

    # 历史最佳记录（仅完赛）
    cursor.execute("""
        SELECT id FROM records
        WHERE user_id = ? AND is_dnf = 0 AND result_time IS NOT NULL
        ORDER BY result_time ASC, id ASC
        LIMIT 1
    """, (user_id,))
    best_row = cursor.fetchone()
    best_id = best_row["id"] if best_row else None

    delete_count = len(rows) - HISTORY_LIMIT
    deleted = 0
    for r in rows:
        if deleted >= delete_count:
            break
        # Golden Record保护：如果最早记录恰好是历史最佳，跳过它，删下一条
        if best_id is not None and r["id"] == best_id:
            continue
        cursor.execute("DELETE FROM records WHERE id = ?", (r["id"],))
        deleted += 1
    db.commit()


class PhysicsEngine:
    """物理引擎封装 - 运行5次取最优"""
    
    @staticmethod
    def validate_strategy(segments: List[Dict]) -> None:
        """验证策略数据合法性"""
        if len(segments) < 9:
            raise HTTPException(status_code=400, detail="Minimum 9 segments required")
        if len(segments) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 segments allowed")
        
        # 检查位置递增
        for i in range(1, len(segments)):
            if segments[i]["now_pos"] <= segments[i-1]["now_pos"]:
                raise HTTPException(status_code=400, detail=f"Telemetry Error / 遥测数据异常: Position must strictly increase at segment {i+1}")
        
        # 检查弯道序列（强校验：必须包含全部9个弯道，且严格按顺序）
        expected_sequence = ['turn1', 'turn2', 'turn4', 'turn6', 'turn7', 'turn8', 'turn10', 'turn12', 'turn13']

        # 若标记 is_corner=true，则必须提供 turn_id
        for i, s in enumerate(segments):
            if s.get("is_corner") and not s.get("turn_id"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Telemetry Error / 遥测数据异常: 第{i+1}段标记为弯道但缺少 turn_id",
                )

        corners = [s for s in segments if s.get("is_corner") and s.get("turn_id")]
        actual_sequence = [c["turn_id"] for c in corners]

        # 必须刚好9个弯道
        if len(actual_sequence) != len(expected_sequence):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Track Sequence Violation / 赛道顺序违规: 必须包含全部9个弯道且按顺序。"
                    f"期望={expected_sequence}，实际={actual_sequence}"
                ),
            )

        # 严格顺序匹配
        if actual_sequence != expected_sequence:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Track Sequence Violation / 赛道顺序违规: 弯道顺序必须严格匹配。"
                    f"期望={expected_sequence}，实际={actual_sequence}"
                ),
            )

        # 弯道段必须包含转向信息（CSV/手动都一致）
        for i, s in enumerate(corners):
            if s.get("steer_LR") not in ("L", "R"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Telemetry Error / 遥测数据异常: 弯道段缺少 steer_LR(L/R)"
                )
            if s.get("steer_degree") is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Telemetry Error / 遥测数据异常: 弯道段缺少 steer_degree"
                )
    
    @staticmethod
    def run_simulation(job_id: str, strategy_df_dict: List[Dict]) -> Dict:
        """运行5次模拟，返回最优结果"""
        import pandas as pd
        import random
        
        # 创建隔离工作目录
        work_dir = TEMP_WORK_DIR / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 准备CSV文件
            csv_path = work_dir / "strategy.csv"
            
            # 转换为DataFrame并确保列名正确
            df_data = []
            for seg in strategy_df_dict:
                row = {
                    "now_pos": seg["now_pos"],
                    "strategy": seg["strategy"],
                    "turn_id": seg.get("turn_id", ""),
                    "steer_L/R": seg.get("steer_LR", ""),
                    "steer_degree": seg.get("steer_degree", 0) if seg.get("is_corner") else 0
                }
                df_data.append(row)
            
            df = pd.DataFrame(df_data)
            df.to_csv(csv_path, index=False)
            
            # 运行5次模拟
            best_result = None
            best_time = float('inf')
            all_results = []
            
            # 复制物理引擎到工作目录（因为引擎会读取本地CSV）
            import shutil
            engine_path = work_dir / "RacingTJ.py"
            shutil.copy(PHYSICS_ENGINE_PATH, engine_path)
            
            for run in range(1, 6):
                # 修改引擎中的CSV路径
                with open(engine_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 使用不同的CSV路径（引擎会读取 drive_strategy_best_df3.csv）
                temp_csv = work_dir / f"strategy_run_{run}.csv"
                df.to_csv(temp_csv, index=False)
                
                # 修改引擎文件中的CSV读取路径
                modified_content = content.replace(
                    "df3 = pd.read_csv('drive_strategy_best_df3.csv')",
                    f"df3 = pd.read_csv('{temp_csv}')"
                )
                modified_engine = work_dir / f"engine_run_{run}.py"
                with open(modified_engine, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                # 执行模拟
                result = subprocess.run(
                    [sys.executable, str(modified_engine)],
                    capture_output=True,
                    text=True,
                    cwd=str(work_dir),
                    timeout=30
                )
                
                # 解析结果（从stdout或生成的CSV）
                # 实际结果需要通过其他方式获取，因为引擎直接print
                # 这里使用导入方式调用
                
            # 使用导入方式更可靠
            import importlib.util
            
            for run in range(1, 6):
                # 使用修改后的引擎文件
                modified_engine = work_dir / f"engine_run_{run}.py"
                spec = importlib.util.spec_from_file_location(f"engine_{run}", modified_engine)
                module = importlib.util.module_from_spec(spec)
                
                # 设置正确的CSV路径
                import pandas as pd
                temp_csv = work_dir / f"strategy_run_{run}.csv"
                df.to_csv(temp_csv, index=False)
                
                # 在模块加载前修改其读取的文件
                original_read_csv = pd.read_csv
                def mock_read_csv(*args, **kwargs):
                    if 'drive_strategy_best_df3.csv' in str(args[0]):
                        return original_read_csv(temp_csv, **kwargs)
                    return original_read_csv(*args, **kwargs)
                
                pd.read_csv = mock_read_csv
                
                try:
                    spec.loader.exec_module(module)
                    # 获取结果
                    if hasattr(module, 'LAP_result'):
                        lap_result = module.LAP_result[1]  # LAP_result2
                        # 规则：
                        # 1) 圈速必须包含罚时（turn_timeloss 累加）
                        # 2) 任意时刻出现 car ruined => 冲出赛道（DNF），该次运行无有效成绩，不能用最后一段 time(s)
                        final_row = lap_result.iloc[-1]
                        car_status = final_row.get('car_status', 'success')

                        details = lap_result.to_dict('records')
                        ruined = False
                        for r in details:
                            st = str(r.get('car_status', 'success')).lower()
                            # 规则补充：任一段出现 failure 视为 ruined（冲出赛道）
                            if st in ('ruined', 'failure'):
                                ruined = True
                                break

                        # 罚时累计
                        penalty = 0.0
                        for r in details:
                            tl = r.get('turn_timeloss', 0)
                            try:
                                penalty += float(tl) if tl is not None else 0.0
                            except Exception:
                                pass

                        base_time = final_row['time(s)']
                        try:
                            base_time = float(base_time)
                        except Exception:
                            base_time = None

                        is_dnf = ruined or (str(car_status).lower() != 'success') or (base_time is None)
                        final_time = None if is_dnf else (base_time + penalty)

                        result_data = {
                            'run': run,
                            'time': final_time,
                            'car_status': 'ruined' if ruined else car_status,
                            'is_dnf': is_dnf,
                            'penalty_time': penalty,
                            'base_time': base_time,
                            'details': details
                        }
                        all_results.append(result_data)
                        
                        if not result_data['is_dnf'] and final_time < best_time:
                            best_time = final_time
                            best_result = result_data
                            
                finally:
                    pd.read_csv = original_read_csv
            
            if best_result is None:
                # 所有运行都失败，取第一次结果
                best_result = all_results[0] if all_results else None
            
            return {
                'job_id': job_id,
                'best_run': best_result['run'] if best_result else None,
                'final_time': best_result['time'] if best_result else None,
                'car_status': best_result['car_status'] if best_result else 'failure',
                'is_dnf': best_result['is_dnf'] if best_result else True,
                'all_runs': all_results,
                'raw_data': best_result['details'] if best_result else None
            }
            
        finally:
            # 清理临时文件
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

# ==========================================
# FastAPI 应用
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    init_db()
    yield
    # 关闭时清理
    pass

app = FastAPI(
    title="商学院赛车策略仿真实验室",
    description="Racing Strategy Simulation Lab for Business School",
    version="5.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# WebSocket 连接管理器
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # 移除无效连接
                self.active_connections.remove(connection)

manager = ConnectionManager()

# ==========================================
# WebSocket 端点
# ==========================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时消息通道"""
    await manager.connect(websocket)
    try:
        while True:
            # 等待客户端消息
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # 处理不同类型的消息
                if message_type == "ping":
                    await manager.send_personal_message({"type": "pong", "timestamp": datetime.now().isoformat()}, websocket)
                elif message_type == "subscribe":
                    # 订阅特定频道 (如 "teacher", "student", "admin")
                    channel = message.get("channel")
                    # 可以在这里实现频道订阅逻辑
                    await manager.send_personal_message({"type": "subscribed", "channel": channel}, websocket)
                else:
                    # 未知消息类型
                    await manager.send_personal_message({"type": "error", "message": "Unknown message type"}, websocket)
            except json.JSONDecodeError:
                await manager.send_personal_message({"type": "error", "message": "Invalid JSON"}, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)

# ==========================================
# 辅助函数：广播全局命令
# ==========================================
async def broadcast_global_command(command: dict):
    """广播全局命令到所有客户端"""
    await manager.broadcast({
        "type": "global_command",
        "data": command,
        "timestamp": datetime.now().isoformat()
    })

# ==========================================
# 认证路由
# ==========================================

@app.post("/api/auth/login")
def login(request: LoginRequest, db=Depends(get_db)):
    """用户登录"""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (request.username,))
    user = cursor.fetchone()
    
    if not user or not verify_password(request.password, user["password_hash"]):
        # 中文优先：主要用户为中文使用者
        raise HTTPException(status_code=401, detail="用户名或密码不匹配")
    
    user_id = user["id"]
    role = user["role"]
    
    # 检查会话限制
    if role == "student":
        # 学生：首入原则
        existing = redis_client.get(f"user_session:{user_id}")
        if existing:
            raise HTTPException(status_code=403, detail="Cockpit Occupied / 驾驶舱已被占用")
    elif role == "teacher":
        # 教师：最多4终端
        session_count = redis_client.scard(f"user_sessions:{user_id}")
        if session_count >= MAX_TEACHER_SESSIONS:
            raise HTTPException(status_code=403, detail="Maximum sessions reached / 会话数已达上限")
    
    # 创建会话
    token = create_session_token()
    expires = datetime.now() + timedelta(hours=8)
    
    cursor.execute("""
        INSERT INTO sessions (user_id, session_token, expires_at) 
        VALUES (?, ?, ?)
    """, (user_id, token, expires))
    db.commit()
    
    # Redis记录
    if role == "student":
        redis_client.setex(f"user_session:{user_id}", 8*3600, token)
    elif role == "teacher":
        redis_client.sadd(f"user_sessions:{user_id}", token)
        redis_client.expire(f"user_sessions:{user_id}", 8*3600)
    
    return {
        "token": token,
        "role": role,
        "display_name": user["display_name"],
        "expires_at": expires.isoformat()
    }

@app.post("/api/auth/logout")
def logout(user=Depends(get_current_user), db=Depends(get_db)):
    """登出"""
    cursor = db.cursor()
    cursor.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (user["session_id"],))
    db.commit()
    
    # 清理Redis
    if user["role"] == "student":
        redis_client.delete(f"user_session:{user['user_id']}")
    elif user["role"] == "teacher":
        redis_client.srem(f"user_sessions:{user['user_id']}", user["token"])
    
    return {"message": "Logged out"}

# ==========================================
# Student 路由
# ==========================================

@app.get("/api/student/status")
def get_student_status(user=Depends(require_role(["student"])), db=Depends(get_db)):
    """获取学生当前状态"""
    cursor = db.cursor()
    
    # 获取当前轮次
    cursor.execute("SELECT * FROM rounds WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    current_round = cursor.fetchone()
    
    if not current_round:
        return {
            "round_active": False,
            "message": "No active round"
        }
    
    # 获取已用次数
    cursor.execute("""
        SELECT COUNT(*) as used FROM records 
        WHERE user_id = ? AND round_id = ?
    """, (user["user_id"], current_round["id"]))
    used = cursor.fetchone()["used"]
    max_attempts = current_round["max_attempts"]
    
    # 获取当前轮次的最佳成绩（所有学生）
    cursor.execute("""
        SELECT u.display_name, MIN(r.result_time) as best_time
        FROM records r
        JOIN users u ON r.user_id = u.id
        WHERE r.round_id = ? AND r.is_dnf = 0 AND r.result_time IS NOT NULL
        GROUP BY r.user_id
        ORDER BY best_time ASC
    """, (current_round["id"],))
    leaderboard = cursor.fetchall()
    
    return {
        "round_active": True,
        "round_number": current_round["round_number"],
        "round_name": current_round["name"],
        "used_attempts": used,
        "max_attempts": max_attempts,
        "remaining": max_attempts - used,
        "leaderboard": [
            {"rank": i+1, "name": row["display_name"], "time": row["best_time"]}
            for i, row in enumerate(leaderboard)
        ],
        "my_position": next((i+1 for i, row in enumerate(leaderboard) if row["display_name"] == user["display_name"]), None)
    }

@app.post("/api/student/submit")
def submit_strategy(
    request: SubmitStrategyRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["student"])),
    db=Depends(get_db)
):
    """提交策略"""
    # 验证策略
    segments = [seg.model_dump() for seg in request.segments]
    PhysicsEngine.validate_strategy(segments)

    # 强制要求策略覆盖完整赛道（避免出现不可能的 25s 这种"半圈"时间）
    if not segments or segments[-1].get("now_pos", 0) < 2820.0:
        raise HTTPException(status_code=400, detail="Strategy must reach finish (now_pos≥2820) / 策略必须覆盖到终点")

    # 获取当前轮次
    cursor = db.cursor()
    cursor.execute("SELECT * FROM rounds WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    current_round = cursor.fetchone()

    if not current_round:
        raise HTTPException(status_code=403, detail="Session Closed / 通道已关闭")

    # Fix 4: 防重入锁——同一学生上次提交仍在计算中时拒绝新提交（防双击/网络抖动）
    inflight_key = f"inflight:{user['user_id']}:{current_round['id']}"
    if redis_client.exists(inflight_key):
        raise HTTPException(
            status_code=429,
            detail={"message": "您的上次提交仍在计算中，请等待结果后再提交"}
        )

    # Fix 3: 队列深度保护——超过 MAX_SIM_QUEUE 时返回 429，防止请求积压超时
    with _sim_queue_lock:
        if _sim_queue >= MAX_SIM_QUEUE:
            raise HTTPException(
                status_code=429,
                detail={"message": "系统仿真队列已满，请稍后重试", "queue_depth": _sim_queue}
            )
        _sim_queue += 1

    try:
        # 原子化分配 attempt_number + 预创建记录
        job_id = create_job_id(user["user_id"])
        strategy_json = json.dumps(segments)

        attempt_number = None
        for _ in range(10):
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute("SELECT is_active FROM rounds WHERE id = ?", (current_round["id"],))
                round_status = cursor.fetchone()
                if not round_status or not round_status["is_active"]:
                    raise HTTPException(status_code=403, detail="Session Closed / 通道已关闭")

                cursor.execute(
                    "SELECT COUNT(*) as count FROM records WHERE user_id = ? AND round_id = ?",
                    (user["user_id"], current_round["id"]),
                )
                used = cursor.fetchone()["count"]
                if used >= current_round["max_attempts"]:
                    raise HTTPException(status_code=403, detail="Out of Laps / 配额耗尽")

                attempt_number = used + 1
                cursor.execute(
                    """
                    INSERT INTO records (job_id, user_id, round_id, attempt_number, strategy_data, is_dnf, car_status)
                    VALUES (?, ?, ?, ?, ?, 1, 2000)
                    """,
                    (job_id, user["user_id"], current_round["id"], attempt_number, strategy_json),
                )
                db.commit()
                break
            except sqlite3.IntegrityError:
                db.rollback()
                attempt_number = None
                continue
            except Exception:
                db.rollback()
                raise

        if attempt_number is None:
            raise HTTPException(status_code=500, detail="Failed to allocate attempt_number")

        # Fix 4: allocation 成功后设置防重入标记（TTL=300s 覆盖最长运行时间）
        redis_client.setex(inflight_key, 300, "1")

        # Fix 2: try/except/finally 确保任何异常路径都清理资源并更新记录状态
        try:
            with SIMULATION_LOCK:
                result = PhysicsEngine.run_simulation(job_id, segments)

            cursor.execute("""
                UPDATE records
                SET result_time = ?, result_data = ?, is_dnf = ?, car_status = ?
                WHERE job_id = ?
            """, (
                result["final_time"],
                json.dumps(result),
                result["is_dnf"],
                2000 if result["is_dnf"] else 100,
                job_id
            ))
            db.commit()

        except HTTPException:
            raise
        except Exception as e:
            # Fix 2: 仿真失败时更新记录（防止幽灵记录无 result_data）
            logger.error(f"simulation failed for job {job_id}: {e}")
            try:
                cursor.execute(
                    "UPDATE records SET is_dnf=1, result_data=? WHERE job_id=?",
                    (json.dumps({"error": str(e)}), job_id)
                )
                db.commit()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="仿真计算失败，请重试")
        finally:
            # Fix 4: 无论成败都释放防重入标记
            redis_client.delete(inflight_key)
            # Fix 2: 双重保险——确保工作目录被清理（run_simulation 内部已有 finally，此为外层保障）
            work_dir = TEMP_WORK_DIR / job_id
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    finally:
        # Fix 3: 无论成败都释放队列计数
        with _sim_queue_lock:
            _sim_queue -= 1

    # FIFO历史清理（含Golden Record保护）
    enforce_history_limit(user["user_id"], db)

    return {
        "job_id": job_id,
        "attempt_number": attempt_number,
        "result": result
    }

@app.post("/api/student/submit-csv")
async def submit_strategy_csv(
    file: UploadFile = File(...),
    user=Depends(require_role(["student"])),
    db=Depends(get_db)
):
    """CSV上传提交策略"""
    import pandas as pd

    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    try:
        from io import StringIO
        df = pd.read_csv(StringIO(content.decode('utf-8')))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid CSV encoding or format")

    required = ["now_pos", "strategy", "turn_id", "steer_L/R", "steer_degree"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required headers: {', '.join(missing)}")

    segments = []
    for _, row in df.iterrows():
        turn_id = "" if pd.isna(row["turn_id"]) else str(row["turn_id"]).strip()
        steer_lr = "" if pd.isna(row["steer_L/R"]) else str(row["steer_L/R"]).strip()
        steer_deg = 0 if pd.isna(row["steer_degree"]) else float(row["steer_degree"])
        segments.append({
            "now_pos": float(row["now_pos"]),
            "strategy": str(row["strategy"]).strip(),
            "is_corner": bool(turn_id),
            "turn_id": turn_id or None,
            "steer_LR": steer_lr or None,
            "steer_degree": steer_deg,
        })

    # 复用提交流程
    PhysicsEngine.validate_strategy(segments)
    if not segments or segments[-1].get("now_pos", 0) < 2820.0:
        raise HTTPException(status_code=400, detail="Strategy must reach finish (now_pos≥2820) / 策略必须覆盖到终点")

    cursor = db.cursor()
    cursor.execute("SELECT * FROM rounds WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    current_round = cursor.fetchone()
    if not current_round:
        raise HTTPException(status_code=403, detail="Session Closed / 通道已关闭")

    # Fix 4: 防重入锁——同一学生上次提交仍在计算中时拒绝新提交
    inflight_key = f"inflight:{user['user_id']}:{current_round['id']}"
    if redis_client.exists(inflight_key):
        raise HTTPException(
            status_code=429,
            detail={"message": "您的上次提交仍在计算中，请等待结果后再提交"}
        )

    # Fix 3: 队列深度保护
    with _sim_queue_lock:
        if _sim_queue >= MAX_SIM_QUEUE:
            raise HTTPException(
                status_code=429,
                detail={"message": "系统仿真队列已满，请稍后重试", "queue_depth": _sim_queue}
            )
        _sim_queue += 1

    try:
        # 原子化分配 attempt_number + 预创建记录（防止同一学生并发上传导致 UNIQUE 冲突）
        job_id = create_job_id(user["user_id"])
        strategy_json = json.dumps(segments)

        attempt_number = None
        for _ in range(10):
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute("SELECT is_active FROM rounds WHERE id = ?", (current_round["id"],))
                round_status = cursor.fetchone()
                if not round_status or not round_status["is_active"]:
                    raise HTTPException(status_code=403, detail="Session Closed / 通道已关闭")

                cursor.execute(
                    "SELECT COUNT(*) as count FROM records WHERE user_id = ? AND round_id = ?",
                    (user["user_id"], current_round["id"]),
                )
                used = cursor.fetchone()["count"]
                if used >= current_round["max_attempts"]:
                    raise HTTPException(status_code=403, detail="Out of Laps / 配额耗尽")

                attempt_number = used + 1
                cursor.execute(
                    """
                    INSERT INTO records (job_id, user_id, round_id, attempt_number, strategy_data, is_dnf, car_status)
                    VALUES (?, ?, ?, ?, ?, 1, 2000)
                    """,
                    (job_id, user["user_id"], current_round["id"], attempt_number, strategy_json),
                )
                db.commit()
                break
            except sqlite3.IntegrityError:
                db.rollback()
                attempt_number = None
                continue
            except Exception:
                db.rollback()
                raise

        if attempt_number is None:
            raise HTTPException(status_code=500, detail="Failed to allocate attempt_number")

        # Fix 4: allocation 成功后设置防重入标记
        redis_client.setex(inflight_key, 300, "1")

        # Fix 2: try/except/finally 确保任何异常路径都清理资源并更新记录状态
        try:
            with SIMULATION_LOCK:
                result = PhysicsEngine.run_simulation(job_id, segments)

            cursor.execute("""
                UPDATE records SET result_time = ?, result_data = ?, is_dnf = ?, car_status = ?
                WHERE job_id = ?
            """, (result["final_time"], json.dumps(result), result["is_dnf"], 2000 if result["is_dnf"] else 100, job_id))
            db.commit()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"simulation failed for job {job_id}: {e}")
            try:
                cursor.execute(
                    "UPDATE records SET is_dnf=1, result_data=? WHERE job_id=?",
                    (json.dumps({"error": str(e)}), job_id)
                )
                db.commit()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="仿真计算失败，请重试")
        finally:
            redis_client.delete(inflight_key)
            work_dir = TEMP_WORK_DIR / job_id
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    finally:
        with _sim_queue_lock:
            _sim_queue -= 1

    enforce_history_limit(user["user_id"], db)

    return {"job_id": job_id, "attempt_number": attempt_number, "result": result}


@app.get("/api/student/history")
def get_history(user=Depends(require_role(["student"])), db=Depends(get_db)):
    """获取历史记录（FIFO 30条）"""
    cursor = db.cursor()
    cursor.execute("""
        SELECT r.*, rounds.round_number
        FROM records r
        JOIN rounds ON r.round_id = rounds.id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
        LIMIT ?
    """, (user["user_id"], HISTORY_LIMIT))
    records = cursor.fetchall()

    return {
        "history": [
            {
                "id": row["id"],
                "round_number": row["round_number"],
                "attempt_number": row["attempt_number"],
                "result_time": row["result_time"],
                "is_dnf": row["is_dnf"],
                "created_at": row["created_at"],
            }
            for row in records
        ]
    }


@app.get("/api/student/history/{record_id}")
def get_history_record(record_id: int, user=Depends(require_role(["student"])), db=Depends(get_db)):
    """获取单条历史记录的详细结果（用于随时下载 telemetry/结果）"""
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT r.*, rounds.round_number
        FROM records r
        JOIN rounds ON r.round_id = rounds.id
        WHERE r.id = ? AND r.user_id = ?
        """,
        (record_id, user["user_id"]),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")

    result_data = None
    if row["result_data"]:
        try:
            result_data = json.loads(row["result_data"])
        except Exception:
            result_data = None

    return {
        "id": row["id"],
        "round_id": row["round_id"],
        "round_number": row["round_number"],
        "attempt_number": row["attempt_number"],
        "result_time": row["result_time"],
        "is_dnf": row["is_dnf"],
        "created_at": row["created_at"],
        "result": result_data,
    }

# ==========================================
# Teacher 路由
# ==========================================

@app.get("/api/teacher/dashboard")
def teacher_dashboard(user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """Teacher 控制面板"""
    cursor = db.cursor()
    
    # 获取当前轮次
    cursor.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1")
    current_round = cursor.fetchone()
    
    # 获取所有学生状态
    cursor.execute("SELECT * FROM users WHERE role = 'student' AND is_active = 1")
    students = cursor.fetchall()
    
    student_status = []
    for student in students:
        # 在线状态
        is_online = redis_client.exists(f"user_session:{student['id']}") > 0
        
        # 本轮提交情况
        if current_round:
            cursor.execute("""
                SELECT COUNT(*) as used,
                       MIN(CASE WHEN is_dnf = 0 AND result_time IS NOT NULL THEN result_time END) as best_time
                FROM records 
                WHERE user_id = ? AND round_id = ?
            """, (student["id"], current_round["id"]))
            stats = cursor.fetchone()
            used = stats["used"] or 0
            best = stats["best_time"]
        else:
            used = 0
            best = None
        
        student_status.append({
            "id": student["id"],
            "username": student["username"],
            "display_name": student["display_name"],
            "online": is_online,
            "used_attempts": used,
            "best_time": best
        })
    
    return {
        "current_round": {
            "id": current_round["id"] if current_round else None,
            "number": current_round["round_number"] if current_round else 0,
            "name": current_round["name"] if current_round else None,
            "is_active": current_round["is_active"] if current_round else False,
            "max_attempts": current_round["max_attempts"] if current_round else 0
        },
        "students": student_status
    }

@app.post("/api/teacher/rounds")
def create_round(request: CreateRoundRequest, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """创建新轮次"""
    cursor = db.cursor()
    
    # 先关闭所有活跃轮次
    cursor.execute("UPDATE rounds SET is_active = 0, ended_at = datetime('now') WHERE is_active = 1")
    
    # 获取新轮次号
    cursor.execute("SELECT COALESCE(MAX(round_number), 0) + 1 FROM rounds")
    next_number = cursor.fetchone()[0]
    
    # 创建新轮次
    auto_end = None
    if request.auto_end_minutes:
        auto_end = datetime.now() + timedelta(minutes=request.auto_end_minutes)
    
    cursor.execute("""
        INSERT INTO rounds (round_number, name, max_attempts, is_active, auto_end_at, started_at, created_by)
        VALUES (?, ?, ?, 1, ?, datetime('now'), ?)
    """, (next_number, request.name, request.max_attempts, auto_end, user["user_id"]))
    
    db.commit()
    
    return {
        "round_number": next_number,
        "message": f"Round {next_number} started"
    }

@app.post("/api/teacher/rounds/{round_id}/stop")
def stop_round(round_id: int, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """强制停止轮次"""
    cursor = db.cursor()
    cursor.execute("""
        UPDATE rounds SET is_active = 0, ended_at = datetime('now')
        WHERE id = ?
    """, (round_id,))
    db.commit()
    return {"message": "Round stopped"}

@app.post("/api/teacher/students/{student_id}/reset-password")
def reset_student_password(student_id: int, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """重置学生密码"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    cursor = db.cursor()
    cursor.execute("""
        UPDATE users SET password_hash = ? WHERE id = ? AND role = 'student'
    """, (hash_password(new_password), student_id))

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    db.commit()
    return {"new_password": new_password}


@app.post("/api/teacher/students/{student_id}/release-session")
def release_student_session(student_id: int, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """强制释放学生驾驶舱占用态（首入原则卡死时使用）"""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ? AND role = 'student' AND is_active = 1", (student_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")

    # DB: deactivate all sessions
    cursor.execute("UPDATE sessions SET is_active = 0 WHERE user_id = ?", (student_id,))
    db.commit()

    # Redis: remove cockpit lock
    redis_client.delete(f"user_session:{student_id}")

    return {"message": "Cockpit released / 驾驶舱已释放"}


@app.get("/api/teacher/export/{round_id}")
def export_round_results(round_id: int, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """按轮次导出最佳成绩CSV"""
    import csv
    export_path = Path(f"/tmp/round_{round_id}_best_results.csv")
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.username, u.display_name,
               MIN(CASE WHEN r.is_dnf = 0 THEN r.result_time END) AS best_time,
               COUNT(r.id) as attempts
        FROM users u
        LEFT JOIN records r ON r.user_id = u.id AND r.round_id = ?
        WHERE u.role = 'student'
        GROUP BY u.id
        ORDER BY best_time IS NULL, best_time ASC
    """, (round_id,))
    rows = cursor.fetchall()

    with export_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["username", "display_name", "best_time", "attempts"])
        for row in rows:
            writer.writerow([row["username"], row["display_name"], row["best_time"], row["attempts"]])

    return FileResponse(path=str(export_path), filename=export_path.name, media_type='text/csv')


@app.get("/api/teacher/rounds/summary")
def teacher_rounds_summary(user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """历史轮次总结：每轮每个学生 attempts / best_time / best_record_id"""
    cursor = db.cursor()

    cursor.execute("SELECT * FROM rounds ORDER BY round_number DESC")
    rounds = cursor.fetchall()

    cursor.execute("SELECT id, username, display_name FROM users WHERE role='student' AND is_active=1 ORDER BY id")
    students = cursor.fetchall()

    out_rounds = []
    for rnd in rounds:
        rid = rnd["id"]
        per_students = []
        for stu in students:
            cursor.execute(
                """
                SELECT
                  COUNT(*) as attempts,
                  MIN(CASE WHEN is_dnf=0 AND result_time IS NOT NULL THEN result_time END) as best_time,
                  (
                    SELECT id FROM records
                    WHERE round_id=? AND user_id=? AND is_dnf=0 AND result_time IS NOT NULL
                    ORDER BY result_time ASC, created_at ASC
                    LIMIT 1
                  ) as best_record_id
                FROM records
                WHERE round_id=? AND user_id=?
                """,
                (rid, stu["id"], rid, stu["id"]),
            )
            st = cursor.fetchone()
            per_students.append(
                {
                    "student_id": stu["id"],
                    "username": stu["username"],
                    "display_name": stu["display_name"],
                    "attempts": st["attempts"] or 0,
                    "best_time": st["best_time"],
                    "best_record_id": st["best_record_id"],
                }
            )

        out_rounds.append(
            {
                "round_id": rid,
                "round_number": rnd["round_number"],
                "name": rnd["name"],
                "max_attempts": rnd["max_attempts"],
                "is_active": bool(rnd["is_active"]),
                "started_at": rnd["started_at"],
                "ended_at": rnd["ended_at"],
                "students": per_students,
            }
        )

    return {"rounds": out_rounds}


@app.get("/api/teacher/records/{record_id}/best-strategy")
def teacher_download_best_strategy(record_id: int, user=Depends(require_role(["teacher"])), db=Depends(get_db)):
    """下载某条 best record 对应的策略 CSV（给老师侧历史轮次总结使用）"""
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT r.id, r.strategy_data, r.round_id, r.user_id, u.username, u.display_name
        FROM records r
        JOIN users u ON r.user_id = u.id
        WHERE r.id = ? AND u.role='student'
        """,
        (record_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")

    # strategy_data is stored as JSON segments
    try:
        segs = json.loads(row["strategy_data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid strategy_data")

    export_path = Path(f"/tmp/record_{record_id}_strategy.csv")
    import csv

    cols = ["now_pos", "strategy", "turn_id", "steer_L/R", "steer_degree"]
    with export_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in segs:
            now_pos = s.get("now_pos")
            strat = s.get("strategy")
            turn_id = s.get("turn_id") or ""
            lr = s.get("steer_LR") or ""
            deg = s.get("steer_degree") if s.get("steer_degree") is not None else ""
            w.writerow([now_pos, strat, turn_id, lr, deg])

    filename = f"BestStrategy-{row['username']}-record_{record_id}.csv"
    return FileResponse(path=str(export_path), filename=filename, media_type='text/csv')

# ==========================================
# Admin 路由 - 使用 token 认证，不需要 localhost 限制
@app.get("/api/admin/teachers")
def list_teachers(user=Depends(require_role(["admin"])), db=Depends(get_db)):
    """列出所有 Teacher"""
    cursor = db.cursor()
    cursor.execute("SELECT id, username, display_name, is_active FROM users WHERE role = 'teacher'")
    return {"teachers": [dict(row) for row in cursor.fetchall()]}

@app.post("/api/admin/teachers/{teacher_id}/reset-password")
def reset_teacher_password(teacher_id: int, request: dict = None, user=Depends(require_role(["admin"])), db=Depends(get_db)):
    """重置 Teacher 密码"""
    req = request or {}
    new_password = req.get("new_password") or "123456"

    cursor = db.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ? AND role = 'teacher'", 
                  (hash_password(new_password), teacher_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Teacher not found")
    db.commit()
    return {"message": "Password reset successfully", "new_password": new_password}

@app.post("/api/admin/teachers")
def create_teacher(request: CreateTeacherRequest, user=Depends(require_role(["admin"])), db=Depends(get_db)):
    """创建 Teacher 账号"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, display_name)
            VALUES (?, ?, 'teacher', ?)
        """, (request.username, hash_password(request.password), request.display_name))
        db.commit()
        return {"message": "Teacher created"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/api/admin/reset-system")
def reset_system(request: ResetSystemRequest, user=Depends(require_role(["admin"])), db=Depends(get_db)):
    """全局重置 - 危险操作"""
    cursor = db.cursor()
    
    # 清空记录和轮次
    cursor.execute("DELETE FROM records")
    cursor.execute("DELETE FROM rounds")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('records', 'rounds')")
    
    # 重置系统配置
    cursor.execute("UPDATE system_config SET current_round = 0, global_reset_at = datetime('now')")
    
    # 重置所有用户状态（可选）
    cursor.execute("UPDATE users SET is_active = 1 WHERE role = 'student'")
    
    db.commit()
    
    # 清理Redis
    redis_client.flushdb()
    
    return {"message": "System reset complete. Ready for Round 1."}

# ==========================================
# 公共路由
# ==========================================

@app.get("/api/health")
async def health_check():
    """Fix 6: 增强健康检查，验证 SQLite 和 Redis 连通性"""
    checks: dict = {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

    # SQLite 检查
    try:
        conn = sqlite3.connect(str(DATABASE_PATH), timeout=5)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["sqlite"] = "ok"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis 检查
    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "degraded"

    # 仿真队列深度
    checks["sim_queue"] = _sim_queue
    checks["max_sim_queue"] = MAX_SIM_QUEUE

    status_code = 200 if checks["status"] == "ok" else 503
    return JSONResponse(content=checks, status_code=status_code)


@app.get("/api/sim-status")
def sim_status():
    """仿真队列状态（供前端轮询）"""
    return {"sim_queue": _sim_queue, "max_sim_queue": MAX_SIM_QUEUE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
