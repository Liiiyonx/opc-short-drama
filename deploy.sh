#!/usr/bin/env bash
# 一键部署脚本（单 VPS，docker compose）
# 用法：bash deploy.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "==> 1/5 检查 Docker 环境"
if ! command -v docker >/dev/null 2>&1; then
    echo "未检测到 docker，请先安装 Docker Engine 与 Compose 插件" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "未检测到 docker compose（v2），请安装 compose 插件" >&2
    exit 1
fi

echo "==> 2/5 检查环境变量文件"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "已生成 .env（来自 .env.example）。"
    echo "！！请先编辑 .env 填入 LLM_API_KEY / JWT_SECRET / 各服务密码，然后重新执行本脚本。"
    exit 0
fi
if grep -q "^LLM_API_KEY=$" .env 2>/dev/null; then
    echo "警告：.env 中 LLM_API_KEY 为空，AI 生成类接口会明确报错（不会静默降级）。"
fi
# 生产凭据预检：缺项/弱密钥在这里给出人话提示，好过容器启动后崩溃循环
missing=()
for var in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD REDIS_PASSWORD MINIO_ROOT_PASSWORD; do
    if grep -q "^${var}=$" .env 2>/dev/null || ! grep -q "^${var}=" .env 2>/dev/null; then
        missing+=("$var")
    fi
done
if [ ${#missing[@]} -gt 0 ]; then
    echo "错误：.env 缺少必填凭据：${missing[*]}（数据面已不暴露公网端口，但内网仍需强口令）" >&2
    exit 1
fi
if grep -q "^JWT_SECRET=opc-dev-secret-change-me-in-production-2026" .env 2>/dev/null; then
    echo "错误：JWT_SECRET 仍为开发默认值，生产（OPC_ENV=prod）会拒绝启动。" >&2
    echo "生成强密钥：openssl rand -hex 32，填入 .env 的 JWT_SECRET 后重试。" >&2
    exit 1
fi

echo "==> 3/5 构建并启动全部服务（mysql/redis/minio/api/worker/web）"
docker compose up -d --build

echo "==> 4/5 等待数据库就绪并执行迁移"
for i in $(seq 1 30); do
    if docker compose exec -T api python -m alembic upgrade head >/dev/null 2>&1; then
        echo "迁移完成"
        break
    fi
    echo "  等待 mysql 就绪（$i/30）..."
    sleep 3
done

echo "==> 5/5 灌入演示数据（幂等）"
docker compose exec -T api python -m scripts.seed || true

echo
echo "部署完成（安全基线：mysql/redis/minio 仅内网互通，未发布公网端口）："
echo "  前端（含 API 反代）  http://<服务器IP>:8080"
echo "  MinIO 控制台         SSH 隧道：ssh -L 9001:127.0.0.1:9001 <user>@<服务器>"
echo
echo "演示账号：admin/admin123、teacher01/teacher123、student01/student123、enterprise01/ent123456"
echo "注意：以上为演示数据口令，上线前必须改密或删除。"
