#!/usr/bin/env bash
# 在「生产服务器」上构建初始数据库:确保迁移到 head → 灌内容种子 → 建正式 admin → 冒烟。
# 前置:已跑过 deploy.sh(镜像/compose/postgres 就绪)、/opt/enggramer/.env 就绪、content_seed.sql 已上传本目录。
# 用法:
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='你的强密码' \
#     bash deploy/build_prod_db.sh [content_seed.sql]
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/enggramer/.env}"
PG="${PG_CONTAINER:-enggramer_postgres}"
NET="${DOCKER_NET:-deploy_internal}"
IMG="${BACKEND_IMAGE:-enggramer-backend:latest}"
SEED="${1:-$(dirname "$0")/content_seed.sql}"

[ -f "$ENV_FILE" ] || { echo "ERROR: 缺 $ENV_FILE"; exit 1; }
[ -f "$SEED" ]     || { echo "ERROR: 缺内容种子 $SEED(先在本机跑 dump_content.sh 并上传)"; exit 1; }
: "${ADMIN_USERNAME:?需设 ADMIN_USERNAME}"; : "${ADMIN_PASSWORD:?需设 ADMIN_PASSWORD(≥8 位)}"

echo "=== [1/4] 迁移到 head(幂等)==="
docker run --rm --network "$NET" --env-file "$ENV_FILE" "$IMG" alembic upgrade head

echo "=== [2/4] 灌内容种子(防重复:已有内容则跳过)==="
CNT=$(docker exec "$PG" psql -U enggramer -d enggramer -tAc \
  "SELECT count(*) FROM vocabulary_words" 2>/dev/null || echo 0)
if [ "${CNT:-0}" -gt 0 ]; then
  echo "  vocabulary_words 已有 $CNT 行 → 判定已灌过,跳过(避免主键冲突/重复)。如需强灌请人工清库后重来。"
else
  docker exec -i "$PG" psql -U enggramer -d enggramer -v ON_ERROR_STOP=1 < "$SEED"
  echo "  内容种子灌入完成。"
fi

echo "=== [3/4] 建正式 admin ==="
docker run --rm --network "$NET" --env-file "$ENV_FILE" \
  -e ADMIN_USERNAME -e ADMIN_PASSWORD "$IMG" python scripts/create_admin.py

echo "=== [4/4] 冒烟:关键表计数 ==="
docker exec "$PG" psql -U enggramer -d enggramer -c "
  SELECT 'vocabulary_words' AS t, count(*) FROM vocabulary_words
  UNION ALL SELECT 'knowledge_nodes', count(*) FROM knowledge_nodes
  UNION ALL SELECT 'platform_question', count(*) FROM platform_question
  UNION ALL SELECT 'vocab_media_asset', count(*) FROM vocab_media_asset
  UNION ALL SELECT 'system_configs', count(*) FROM system_configs
  UNION ALL SELECT 'users(应=1,只有admin)', count(*) FROM users;"

echo ""
echo "✓ 生产 DB 构建完成。用 $ADMIN_USERNAME 登录 admin 验证。"
