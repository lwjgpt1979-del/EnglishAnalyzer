#!/usr/bin/env bash
# engGramer 数据库每日备份（上线硬化）
# 用法：
#   chmod +x deploy/backup_db.sh
#   crontab -e  → 0 3 * * * /opt/enggramer/deploy/backup_db.sh >> /var/log/enggramer-backup.log 2>&1
# 依赖：docker（postgres 容器）、gzip；可选 coscmd（上传 COS 异地副本）。
set -euo pipefail

# ── 可配置项（按生产环境改）────────────────────────────────────────────────
PG_CONTAINER="${PG_CONTAINER:-enggramer-postgres}"
PG_USER="${PG_USER:-enggramer}"
PG_DB="${PG_DB:-enggramer}"
LOCAL_DIR="${BACKUP_DIR:-/var/backups/enggramer}"
LOCAL_KEEP_DAYS="${LOCAL_KEEP_DAYS:-7}"     # 本地保留天数
COS_PREFIX="${COS_PREFIX:-/backups}"        # COS 路径前缀（配了 coscmd 才上传）
COS_ENABLED="${COS_ENABLED:-0}"             # 1=上传 COS

TS="$(date +%F_%H%M%S)"
OUT="${LOCAL_DIR}/db-${TS}.sql.gz"
mkdir -p "${LOCAL_DIR}"

echo "[$(date +%FT%T)] 开始备份 ${PG_DB} → ${OUT}"

# ── 全量导出 + 压缩 ─────────────────────────────────────────────────────────
docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" "${PG_DB}" | gzip -9 > "${OUT}"

# ── 完整性校验：gzip -t + 非空 ───────────────────────────────────────────────
if ! gzip -t "${OUT}"; then
  echo "❌ 备份文件 gzip 校验失败，删除残档并退出" >&2
  rm -f "${OUT}"
  exit 1
fi
SIZE=$(stat -c%s "${OUT}" 2>/dev/null || stat -f%z "${OUT}")
if [ "${SIZE}" -lt 1024 ]; then
  echo "❌ 备份文件过小（${SIZE}B），疑似失败，退出" >&2
  exit 1
fi
echo "✅ 本地备份完成（${SIZE} 字节）"

# ── 异地副本（COS）──────────────────────────────────────────────────────────
if [ "${COS_ENABLED}" = "1" ] && command -v coscmd >/dev/null 2>&1; then
  coscmd upload "${OUT}" "${COS_PREFIX}/db-${TS}.sql.gz" && echo "✅ 已上传 COS"
else
  echo "ℹ️ 跳过 COS 上传（COS_ENABLED=${COS_ENABLED}）"
fi

# ── 本地轮转 ────────────────────────────────────────────────────────────────
find "${LOCAL_DIR}" -name "db-*.sql.gz" -mtime "+${LOCAL_KEEP_DAYS}" -delete
echo "[$(date +%FT%T)] 备份结束；本地保留近 ${LOCAL_KEEP_DAYS} 天"
