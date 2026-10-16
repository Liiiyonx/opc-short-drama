#!/usr/bin/env bash
# ============================================================
# OPC 短剧出海平台 · 一键启动演示环境
#   启动：API(8000) + arq worker + 前端 dev(5199)，并做健康检查
# 用法：
#   bash demo_up.sh           # 真实 AI 模式（需 opc_secrets.env）
#   bash demo_up.sh --mock    # 无密钥演示模式（全程离线可跑）
# 停止：bash demo_down.sh
# ============================================================
set -u

BASE="$(cd "$(dirname "$0")" && pwd)"
DEMO_DIR="$BASE/.demo"
mkdir -p "$DEMO_DIR"

MOCK_MODE=0
[ "${1:-}" = "--mock" ] && MOCK_MODE=1

# ---------- 定位可用的 Python（必须具备项目依赖） ----------
PY=""
CANDIDATES=(
  "${PYTHON:-}"
  "$BASE/backend/.venv/Scripts/python.exe"
  "$HOME/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
  "C:/Users/Liii/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
  "$(command -v python3 2>/dev/null)"
  "$(command -v python 2>/dev/null)"
)
for cand in "${CANDIDATES[@]}"; do
  [ -n "$cand" ] && [ -x "$cand" ] || continue
  if "$cand" -c "import fastapi, uvicorn, arq, edge_tts, sqlalchemy" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "✗ 未找到具备项目依赖的 Python。请先安装依赖："
  echo "  cd backend && python -m venv .venv"
  echo "  Windows Git Bash:  source .venv/Scripts/activate && pip install -r requirements.txt"
  echo "  或指定解释器：PYTHON=/path/to/python bash demo_up.sh"
  exit 1
fi
echo "✓ Python：$PY"

# ---------- 密钥（存在才加载，不回显） ----------
SECRETS="D:/VeriCall_data/secrets/opc_secrets.env"
if [ "$MOCK_MODE" = "0" ] && [ -f "$SECRETS" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$SECRETS"
  set +a
  echo "✓ 已加载密钥文件：$SECRETS"
elif [ "$MOCK_MODE" = "1" ]; then
  export LLM_PROVIDER=mock
  export TTS_PROVIDER=mock
  echo "✓ mock 模式：LLM 与 TTS 均使用测试桩（无需密钥）"
else
  echo "! 未找到密钥文件 $SECRETS（将以 mock 模式启动演示）"
  export LLM_PROVIDER=mock
  export TTS_PROVIDER=mock
fi

# 演示环境放宽媒体配额（避免彩排反复生成撞 10 次/天）
export QUOTA_MEDIA_CALLS_PER_USER_DAY="${QUOTA_MEDIA_CALLS_PER_USER_DAY:-100}"

# ---------- 依赖快检 ----------
command -v ffmpeg >/dev/null 2>&1 || echo "! 未找到 ffmpeg（配音/成片将失败）"
(echo > /dev/tcp/127.0.0.1/6379) 2>/dev/null || echo "! Redis 6379 不可达（异步任务将失败）"

# ---------- 数据库初始化（幂等） ----------
cd "$BASE/backend" || exit 1
"$PY" -m alembic upgrade head >/dev/null 2>&1 || echo "! 数据库迁移失败，请手动检查"
"$PY" -m scripts.seed >/dev/null 2>&1 || echo "! 演示数据播种失败（可忽略，继续启动）"

# ---------- 启动服务 ----------
echo "→ 启动 worker / API / 前端…"
( "$PY" -m arq app.workers.tasks.WorkerSettings > "$DEMO_DIR/worker.log" 2>&1 & echo $! > "$DEMO_DIR/worker.pid" )
( "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$DEMO_DIR/api.log" 2>&1 & echo $! > "$DEMO_DIR/api.pid" )

cd "$BASE/frontend" || exit 1
if [ ! -d node_modules ]; then
  echo "→ 首次运行：安装前端依赖（npm install）…"
  npm install >/dev/null 2>&1
fi
( VITE_API_TARGET=http://127.0.0.1:8000 npm run dev -- --port 5199 --strictPort > "$DEMO_DIR/vite.log" 2>&1 & echo $! > "$DEMO_DIR/vite.pid" )

# ---------- 健康检查 ----------
echo "→ 健康检查…"
API_OK=0
for _ in $(seq 1 40); do
  if curl -s -m 2 http://127.0.0.1:8000/health 2>/dev/null | grep -q '"status"'; then
    API_OK=1
    break
  fi
  sleep 1
done
WEB_OK=0
for _ in $(seq 1 40); do
  if curl -s -m 2 http://127.0.0.1:5199/ 2>/dev/null | grep -q "OPC\|<div id=\"app\""; then
    WEB_OK=1
    break
  fi
  sleep 1
done

echo ""
echo "==================== OPC 演示环境 ===================="
[ "$API_OK" = "1" ] && echo "✓ 后端 API      http://127.0.0.1:8000/docs" || echo "✗ 后端 API 未就绪（看 .demo/api.log）"
[ "$WEB_OK" = "1" ] && echo "✓ 前端工坊      http://127.0.0.1:5199  ← 浏览器打开" || echo "✗ 前端未就绪（看 .demo/vite.log）"
echo "  运行模式      $([ "$MOCK_MODE" = "1" ] && echo 'mock 桩' || echo "真实 AI（${LLM_MODEL_DEFAULT:-deepseek-v4-flash}）")"
echo "  演示账号      student01/student123 · teacher01/teacher123 · enterprise01/ent123456"
echo "  日志目录      .demo/{api,worker,vite}.log"
echo "  停止服务      bash demo_down.sh"
echo "======================================================"
