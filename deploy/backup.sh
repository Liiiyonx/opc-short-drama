#!/usr/bin/env bash
# ============================================================
# OPC 平台一键备份：MySQL 全量 + MinIO 数据（滚动保留 7 份）
# 用法：bash deploy/backup.sh
# 建议 crontab（每日 03:00）：
#   0 3 * * * cd /path/to/opc && bash deploy/backup.sh >> backups/backup.log 2>&1
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP=7
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "==> 1/3 MySQL 全量导出"
docker compose exec -T mysql sh -c 'exec mysqldump --single-transaction -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  | gzip > "$BACKUP_DIR/db_$STAMP.sql.gz"

echo "==> 2/3 MinIO 对象存储打包"
docker compose exec -T minio tar -cf - /data 2>/dev/null | gzip > "$BACKUP_DIR/minio_$STAMP.tar.gz"

echo "==> 3/3 滚动清理（保留最近 $KEEP 份）"
ls -1t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
ls -1t "$BACKUP_DIR"/minio_*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo
echo "✓ 备份完成："
ls -lh "$BACKUP_DIR"/db_$STAMP.sql.gz "$BACKUP_DIR"/minio_$STAMP.tar.gz
echo
echo "恢复提示："
echo "  数据库：gunzip < db_*.sql.gz | docker compose exec -T mysql sh -c 'exec mysql -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\"'"
echo "  对象：docker compose cp minio_*.tar.gz minio:/tmp && docker compose exec minio sh -c 'cd / && tar -xf /tmp/…'"
