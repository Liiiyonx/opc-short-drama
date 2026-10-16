#!/usr/bin/env bash
# 停止 demo_up.sh 启动的全部服务。
set -u
BASE="$(cd "$(dirname "$0")" && pwd)"
DEMO_DIR="$BASE/.demo"

for name in api worker vite; do
  PID_FILE="$DEMO_DIR/$name.pid"
  if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if kill "$PID" 2>/dev/null; then
      echo "✓ 已停止 $name（pid $PID）"
    else
      echo "! $name（pid $PID）未在运行"
    fi
    rm -f "$PID_FILE"
  fi
done
# 兜底清理（防止 pid 文件丢失时残留）
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "arq app.workers.tasks" 2>/dev/null
pkill -f "vite --port 5199" 2>/dev/null
echo "演示环境已停止。"
