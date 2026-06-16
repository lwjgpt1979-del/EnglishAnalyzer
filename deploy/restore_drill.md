# 数据库恢复演练（上线前必做一次，之后季度演练）

> 备份只有"能恢复"才算数。上线前务必在**非生产**环境完整跑通一次本流程，并记录耗时（RTO）。

## 0. 准备
- 一份真实备份：`deploy/backup_db.sh` 产出的 `db-YYYY-MM-DD_HHMMSS.sql.gz`
- 一个**空的**演练库容器（切勿对生产库演练）：

```bash
docker run -d --name pg-drill -e POSTGRES_USER=enggramer \
  -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=enggramer -p 55432:5432 postgres:16
```

## 1. 恢复
```bash
gunzip -c db-2026-06-16_030000.sql.gz | \
  docker exec -i pg-drill psql -U enggramer -d enggramer
```

## 2. 校验（关键表行数 + 迁移版本一致）
```bash
docker exec pg-drill psql -U enggramer -d enggramer -c \
  "SELECT 'users' t, count(*) FROM users
   UNION ALL SELECT 'orders', count(*) FROM orders
   UNION ALL SELECT 'memberships', count(*) FROM memberships
   UNION ALL SELECT 'alembic', count(*) FROM alembic_version;"
# alembic_version 应与生产 head 一致（当前 m79_rate_limits）
docker exec pg-drill psql -U enggramer -d enggramer -c "SELECT version_num FROM alembic_version;"
```

## 3. 起一份后端连到演练库，冒烟
```bash
ASYNC_DATABASE_URL=postgresql+psycopg://enggramer:drill@localhost:55432/enggramer \
  uvicorn app.main:app --port 8001
# 浏览器/curl 验证 /docs（debug）或关键只读接口能返回数据
```

## 4. 记录 & 清理
- 记录：备份大小、恢复耗时（gunzip+psql）、校验结果 → 填入运维台账。
- `docker rm -f pg-drill`

## 验收标准
- [ ] 恢复无报错；关键表行数与备份时点吻合
- [ ] alembic_version = 生产 head
- [ ] 后端连演练库可正常读数
- [ ] RTO（恢复耗时）记录在案，且在可接受范围
