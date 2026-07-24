#!/usr/bin/env bash
# 从「开发库」导出仅「内容/缓存/配置」表的数据(不含用户/学习/日志/alembic_version)。
# 产物 content_seed.sql 用于生产:生产先 alembic upgrade head 建好结构,再灌这个文件。
#   本机运行:  bash deploy/dump_content.sh  [输出文件=content_seed.sql]
# 依赖:本机 docker + 开发库容器(默认 enggramer-pg-dev,库 enggramer,超管 postgres)。
set -euo pipefail

PGC="${PG_CONTAINER:-enggramer-pg-dev}"
PGUSER="${PG_USER:-postgres}"
DBDEV="${DB_DEV:-enggramer}"
OUT="${1:-content_seed.sql}"

# KEEP 名单(已确认;不含 alembic_version——生产版本由 upgrade head 决定,导它会污染)。
KEEP=(
  vocabulary_words vocab_list vocab_list_item vocab_word_relation vocab_word_sense
  vocab_word_kp vocab_word_kp_review vocab_kp_mcq vocab_kp_mcq_revision vocab_media_asset
  vocab_image_verify_cache vocab_review vocab_node knowledge_nodes knowledge_node_aliases
  kp_candidates ai_questions platform_question platform_question_kp curriculum_units
  curriculum_words unit_node kp_lecture grammar_lecture_cache sentence_analysis_cache
  ocr_cache paper_split_cache kp_classify_cache reading_analysis_cache reading_practice_cache
  system_configs
  passage unit_sections unit_section_sentences   # 教材结构化(有就带,没有自动跳过)
)

# 只保留「库里真实存在」的表(passage/unit_section* 可能不存在)
EXIST=$(docker exec "$PGC" psql -U "$PGUSER" -d "$DBDEV" -tAc \
  "SELECT tablename FROM pg_tables WHERE schemaname='public'")
ARGS=(); INCLUDED=()
for t in "${KEEP[@]}"; do
  if grep -qxF "$t" <<<"$EXIST"; then ARGS+=(-t "$t"); INCLUDED+=("$t"); fi
done
echo "将导出 ${#INCLUDED[@]} 张表:${INCLUDED[*]}"

# 待清表(以开发库内容为准):部分表迁移会预置数据(如 knowledge_nodes),不先清会主键冲突
TRUNC=$(IFS=,; echo "${INCLUDED[*]}")

{
  echo "-- engGramer 内容种子(仅内容/缓存/配置,无用户/日志)。生产 alembic upgrade head 后灌入。"
  echo "-- 生成自开发库 ${DBDEV}@${PGC}"
  echo "SET session_replication_role = replica;  -- 全程关外键/触发,免加载顺序 FK 报错"
  echo "TRUNCATE ${TRUNC} RESTART IDENTITY CASCADE;  -- 清掉迁移预置内容,以开发库为准(全新生产库仅空用户表被级联,无害)"
  # 纯 COPY 数据(session_replication_role 已关触发,无需 --disable-triggers)
  docker exec "$PGC" pg_dump -U "$PGUSER" -d "$DBDEV" \
    --data-only --no-owner --no-privileges "${ARGS[@]}"
  echo ""
  echo "-- pg_dump 头部会把 search_path 清空,恢复它,否则下面不带 schema 的语句报表不存在"
  echo "SELECT pg_catalog.set_config('search_path', 'public', false);"
  echo "-- 审计字段 updated_by 指向已清空的 admin,置空(字段可空,仅记录谁改的),否则悬空外键"
  echo "UPDATE system_configs SET updated_by = NULL;"
  echo "SET session_replication_role = DEFAULT;"
} > "$OUT"

echo "✓ 导出完成:$OUT ($(wc -l < "$OUT" | tr -d ' ') 行,$(du -h "$OUT" | cut -f1))"
echo "  下一步:把 $OUT 传到服务器,跑 deploy/build_prod_db.sh"
