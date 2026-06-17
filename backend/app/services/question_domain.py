"""R0.5 题分域配套工具:应用层域隔离 + answer_log 月分区。

决策④:不引入 PG RLS(项目现状即应用层过滤),用 scoped() 统一强制按 scope/owner 过滤。
决策⑤:answer_log 建表即月分区,本助手按需建月分区(R0 无数据,留作 R3/R4 调用)。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def scoped(stmt, scope_col, scope_val, owner_col=None, owner_id=None):
    """给查询强制加域过滤:scope_col == scope_val [AND owner_col == owner_id]。

    用法(机构/个人题、语料):
        scoped(select(UploadedQuestion), UploadedQuestion.owner_scope, "student",
               UploadedQuestion.owner_id, student_id)
    平台域只读引用通常不带 owner(全员共享),只过 scope。
    """
    stmt = stmt.where(scope_col == scope_val)
    if owner_col is not None and owner_id is not None:
        stmt = stmt.where(owner_col == owner_id)
    return stmt


def answer_log_partition_name(year: int, month: int) -> str:
    return f"answer_log_{year:04d}{month:02d}"


def answer_log_partition_ddl(year: int, month: int) -> str:
    """某年月的 answer_log 月分区 DDL([当月1日, 次月1日) 半开区间)。"""
    if not (1 <= month <= 12):
        raise ValueError("month 必须 1–12")
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    name = answer_log_partition_name(year, month)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF answer_log "
        f"FOR VALUES FROM ('{year:04d}-{month:02d}-01') TO ('{ny:04d}-{nm:02d}-01')"
    )


async def create_answer_log_partition(db: AsyncSession, year: int, month: int) -> str:
    """建某年月的 answer_log 分区(幂等,IF NOT EXISTS),返回分区名。"""
    await db.execute(sa.text(answer_log_partition_ddl(year, month)))
    return answer_log_partition_name(year, month)
