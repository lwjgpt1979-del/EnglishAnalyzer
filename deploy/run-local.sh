#!/usr/bin/env bash
# deploy/run-local.sh — 本机 Docker 一键启动脚本
# 用法：cd deploy && bash run-local.sh
# 或：cd 项目根目录 && bash deploy/run-local.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==> [1/4] 构建后端 Docker 镜像…"
docker build -t enggramer-backend:latest "$PROJECT_ROOT/backend"

echo "==> [2/4] 启动 postgres + backend…"
docker compose -p local -f "$SCRIPT_DIR/docker-compose.local.yml" up -d

echo "==> [3/4] 等待 postgres 就绪…"
until docker exec enggramer_local_postgres pg_isready -U enggramer -d enggramer >/dev/null 2>&1; do
  printf '.'
  sleep 2
done
echo " ready!"

echo "==> [3b/4] 运行 Alembic 数据库迁移…"
docker exec enggramer_local_backend \
  bash -c "cd /app && alembic upgrade head"

echo "==> [4/4] 验证健康检查…"
sleep 3
curl -sf http://localhost:8000/health && echo ""

echo ""
echo "✅ 本地环境启动成功！"
echo ""
echo "  API 根地址:   http://localhost:8000"
echo "  健康检查:     curl http://localhost:8000/health"
echo "  API 文档:     http://localhost:8000/docs"
echo "  PostgreSQL:   localhost:5433 (user: enggramer / local_dev_password)"
echo ""
echo "停止服务: docker compose -p local -f deploy/docker-compose.local.yml down"
echo "查看日志: docker logs -f enggramer_local_backend"
