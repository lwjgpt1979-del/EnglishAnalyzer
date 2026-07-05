"""平台级操作审计查询(写入走 app/core/audit_middleware.py,业务零埋点)。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d9_system import AdminAuditLog

MODULES = ("sales", "finance", "ops", "teacher_inst", "system", "support",
           "vocab", "speak", "content")


async def list_logs(db: AsyncSession, *, module: str | None = None,
                    method: str | None = None, admin_id: uuid.UUID | None = None,
                    q: str | None = None, status_min: int | None = None,
                    date_from: datetime | None = None, date_to: datetime | None = None,
                    skip: int = 0, limit: int = 50) -> dict:
    """分页查审计。q 模糊匹配路径;status_min=400 可只看失败/越权。"""
    conds = []
    if module:
        conds.append(AdminAuditLog.module == module)
    if method:
        conds.append(AdminAuditLog.method == method.upper())
    if admin_id is not None:
        conds.append(AdminAuditLog.admin_id == admin_id)
    if q:
        conds.append(AdminAuditLog.path.ilike(f"%{q}%"))
    if status_min is not None:
        conds.append(AdminAuditLog.status >= status_min)
    if date_from is not None:
        conds.append(AdminAuditLog.created_at >= date_from)
    if date_to is not None:
        conds.append(AdminAuditLog.created_at <= date_to)

    total = (await db.execute(
        sa.select(sa.func.count()).select_from(AdminAuditLog).where(*conds))).scalar() or 0
    rows = (await db.execute(
        sa.select(AdminAuditLog, User.username, User.nickname)
        .join(User, User.id == AdminAuditLog.admin_id, isouter=True)
        .where(*conds)
        .order_by(AdminAuditLog.created_at.desc())
        .offset(skip).limit(limit))).all()

    return {"total": total, "items": [{
        "id": str(r.AdminAuditLog.id),
        "admin_id": str(r.AdminAuditLog.admin_id) if r.AdminAuditLog.admin_id else None,
        "admin_name": r.username or r.nickname or (None if r.AdminAuditLog.admin_id is None else "已删除账号"),
        "method": r.AdminAuditLog.method, "path": r.AdminAuditLog.path,
        "module": r.AdminAuditLog.module, "status": r.AdminAuditLog.status,
        "query": r.AdminAuditLog.query, "detail": r.AdminAuditLog.detail,
        "ip": r.AdminAuditLog.ip, "duration_ms": r.AdminAuditLog.duration_ms,
        "created_at": r.AdminAuditLog.created_at.isoformat(),
    } for r in rows]}


async def admin_options(db: AsyncSession) -> list[dict]:
    """出现过的操作人下拉(去重)。"""
    rows = (await db.execute(
        sa.select(AdminAuditLog.admin_id, User.username, User.nickname)
        .join(User, User.id == AdminAuditLog.admin_id, isouter=True)
        .where(AdminAuditLog.admin_id.is_not(None))
        .group_by(AdminAuditLog.admin_id, User.username, User.nickname))).all()
    return [{"admin_id": str(r.admin_id), "name": r.username or r.nickname or "已删除账号"}
            for r in rows]
