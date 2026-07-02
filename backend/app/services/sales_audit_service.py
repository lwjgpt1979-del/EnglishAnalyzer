"""电销 CRM 操作审计:记录 + 查询线索流转留痕。

在 claim/release/assign/merge/status_change 等动作点调 record(...);只增不改。
独立成文件,便于各处埋点复用(避免耦合进 sales_crm_service 的业务函数)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d23_sales_crm import SalesAuditLog

ACTIONS = ("create", "import", "claim", "release", "assign", "merge",
           "status_change", "dnc", "update", "auto_assign", "recycle")


async def record(
    db: AsyncSession, *, admin_id: uuid.UUID | None, action: str,
    lead_id: uuid.UUID | None = None, detail: dict | None = None,
) -> None:
    """写一条审计(不 commit,随调用方事务落库)。非法 action 归一为 update。"""
    db.add(SalesAuditLog(
        id=uuid.uuid4(), admin_id=admin_id,
        action=action if action in ACTIONS else "update",
        lead_id=lead_id, detail=detail))
    await db.flush()


async def list_audit(
    db: AsyncSession, *, lead_id: uuid.UUID | None = None,
    admin_id: uuid.UUID | None = None, action: str | None = None,
    skip: int = 0, limit: int = 20,
) -> tuple[list[SalesAuditLog], int]:
    base = sa.select(SalesAuditLog)
    if lead_id is not None:
        base = base.where(SalesAuditLog.lead_id == lead_id)
    if admin_id is not None:
        base = base.where(SalesAuditLog.admin_id == admin_id)
    if action:
        base = base.where(SalesAuditLog.action == action)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(SalesAuditLog.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total
