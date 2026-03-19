module.exports = {
  apps: [
    {
      name: "racing-backend",
      cwd: "/Users/macmini/.openclaw/workspace/racing-sim/backend",
      script: "python3",
      // Fix 5: 配置 uvicorn 线程池上限 + keepalive 超时（覆盖物理引擎最大运行时间）
      args: [
        "-c",
        "import sys; sys.path.insert(0, '/Users/macmini/.openclaw/workspace/racing-sim/backend'); import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=8000, workers=1, loop='asyncio', http='h11', timeout_keep_alive=65, limit_concurrency=30, log_level='warning')"
      ],
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s",
      env: {
        PYTHONPATH: "/Users/macmini/.openclaw/workspace/racing-sim/backend",
        PYTHONUNBUFFERED: "1"
      },
      log_file: "/tmp/racing_backend.log"
    },
    {
      name: "racing-frontend",
      cwd: "/Users/macmini/.openclaw/workspace/racing-sim/frontend",
      script: "npx",
      args: ["vite", "--port", "5173"],
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s",
      env: {
        NODE_ENV: "development"
      }
    },
    {
      name: "racing-tunnel",
      script: "cloudflared",
      args: "tunnel run racing-app",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s"
    }
  ]
};
