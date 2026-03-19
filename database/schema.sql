-- 商学院赛车策略仿真实验室 - 数据库Schema
-- SQLite Database Schema

-- 1. 用户表 (Admin/Teacher/Student)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
    display_name TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 会话表 (管理登录会话)
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token TEXT UNIQUE NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. 轮次表 (Round Management)
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number INTEGER NOT NULL,
    name TEXT,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    is_active BOOLEAN DEFAULT 0,
    auto_end_at TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id),
    UNIQUE(round_number)
);

-- 4. 提交记录表 (Records)
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    round_id INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    strategy_data TEXT NOT NULL, -- JSON格式存储策略
    result_time REAL,
    result_data TEXT, -- JSON格式存储完整结果
    is_dnf BOOLEAN DEFAULT 0, -- Did Not Finish
    car_status INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (round_id) REFERENCES rounds(id),
    UNIQUE(user_id, round_id, attempt_number)
);

-- 5. 系统配置表
CREATE TABLE IF NOT EXISTS system_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_round INTEGER DEFAULT 0,
    global_reset_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初始化数据 (如果表为空)
-- Admin账号 (密码需要在应用层哈希后插入)
INSERT OR IGNORE INTO users (username, password_hash, role, display_name) VALUES
('admin', '', 'admin', 'System Administrator');

-- 系统配置
INSERT OR IGNORE INTO system_config (id, current_round) VALUES (1, 0);

-- 索引优化
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_records_user_round ON records(user_id, round_id);
CREATE INDEX IF NOT EXISTS idx_records_job ON records(job_id);
CREATE INDEX IF NOT EXISTS idx_rounds_active ON rounds(is_active);
