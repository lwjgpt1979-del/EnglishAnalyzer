"""敏感操作二次审批(maker-checker)admin API。

待审批列表 / 复核(批准即回放执行,驳回关单)/ 阈值配置。独立模块,避免与 admin.py 撞车。
复核人必须 ≠ 发起人。挂在 AdminDep(platform_admin + 模块权限由 admin.py 的 module_map 统管)。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import approval_service

router = APIRouter(prefix="/admin/approvals", tags=["admin-approval"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class DecideIn(BaseModel):
    approve: bool
    note: str | None = None


class ConfigIn(BaseModel):
    enabled: bool | None = None
    refund_amount_fen: int | None = None
    coupon_grant_count: int | None = None


@router.get("", response_model=BaseResponse[dict])
async def list_approvals(
    db: DbDep, admin: AdminDep,
    status: str = Query("pending", description="pending | executed | rejected | failed | all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """待审批(默认)/ 历史列表,分页。"""
    items, total = await approval_service.list_approvals(
        db, status=status, skip=skip, limit=limit)
    return make_ok({"total": total, "items": items})


@router.post("/{approval_id}/decide", response_model=BaseResponse[dict])
async def decide(approval_id: uuid.UUID, body: DecideIn, db: DbDep, admin: AdminDep):
    """复核:批准 → 回放执行敏感操作;驳回 → 关单。复核人须 ≠ 发起人。"""
    ap = await approval_service.decide(
        db, approval_id=approval_id, checker=admin, approve=body.approve, note=body.note)
    await db.commit()
    return make_ok({"id": str(ap.id), "status": ap.status})


@router.get("/config", response_model=BaseResponse[dict])
async def get_config(db: DbDep, admin: AdminDep):
    """当前审批阈值配置。"""
    return make_ok(await approval_service.get_config(db))


@router.put("/config", response_model=BaseResponse[dict])
async def update_config(body: ConfigIn, db: DbDep, admin: AdminDep):
    """改审批阈值(运营可配)。"""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = await approval_service.update_config(db, patch=patch, updated_by=admin.id)
    await db.commit()
    return make_ok(cfg)
