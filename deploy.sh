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
    echo "！！请先编辑 .env 填入 LLM_API_KEY（DeepSeek）等密钥，然后重新执行本脚本。"
    exit 0
fi
if grep -q "^LLM_API_KEY=$" .env 2>/dev/null; then
    echo "警告：.env 中 LLM_API_KEY 为空，AI 生成类接口会明确报错（不会静默降级）。"
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
echo "部署完成："
echo "  前端      http://<服务器IP>:8080"
echo "  API 文档  http://<服务器IP>:8000/docs"
echo "  MinIO 控制台 http://<服务器IP>:9001"
echo
echo "演示账号：admin/admin123、teacher01/teacher123、student01/student123、enterprise01/ent123456"
echo "注意：以上为演示数据口令，上线前必须改密或删除。"
