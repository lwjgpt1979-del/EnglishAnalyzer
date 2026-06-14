"""权益体系 API（步骤1：只读能力图 + 后台配置；不改现有门禁行为）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import entitlement_service

router = APIRouter(prefix="/me", tags=["entitlements"])
admin_router = APIRouter(prefix="/admin/entitlements", tags=["admin-entitlements"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


@router.get("/entitlements", response_model=BaseResponse[dict])
async def my_entitlements(db: DbDep, current_user: UserDep):
    """当前用户对所有能力的有效结果图（前端做锁标/配额/弹墙）。"""
    return make_ok(await entitlement_service.me_entitlements(db, user_id=current_user.id))


@admin_router.get("", response_model=BaseResponse[dict])
async def list_entitlements(db: DbDep, admin: AdminDep):
    """注册表全集 + 当前覆盖（后台可视化配置）。"""
    return make_ok(await entitlement_service.admin_list(db))


class OverrideIn(BaseModel):
    feature_key: str
    tier: str
    mode: str                      # allow / deny / quota
    quota_limit: int | None = None
    quota_period: str | None = None


@admin_router.put("", response_model=BaseResponse[dict])
async def set_override(body: OverrideIn, db: DbDep, admin: AdminDep):
    await entitlement_service.admin_set_override(
        db, key=body.feature_key, tier=body.tier, mode=body.mode,
        limit=body.quota_limit, period=body.quota_period, updated_by=admin.id)
    await db.commit()
    return make_ok(await entitlement_service.admin_list(db))


@admin_router.delete("", response_model=BaseResponse[dict])
async def clear_override(feature_key: str, tier: str, db: DbDep, admin: AdminDep):
    await entitlement_service.admin_clear_override(db, key=feature_key, tier=tier)
    await db.commit()
    return make_ok(await entitlement_service.admin_list(db))
