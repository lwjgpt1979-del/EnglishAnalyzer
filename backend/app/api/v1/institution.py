"""机构管理员后台 API（D-120）。

鉴权：require_role("institution_admin")；所有查询以 current_user.institution_id
为隔离键，机构只能看自己的数据。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.institution import (
    InstitutionOverviewOut,
    InstitutionProfileOut,
    InstitutionProfileUpdate,
)
from app.services import institution_service

router = APIRouter(prefix="/institution", tags=["institution"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
InstAdminDep = Annotated[User, Depends(require_role("institution_admin"))]


def _require_inst(admin: User):
    if admin.institution_id is None:
        raise AppError(code=400, message="该管理员未绑定机构")
    return admin.institution_id


@router.get("/overview", response_model=BaseResponse[InstitutionOverviewOut])
async def get_overview(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    data = await institution_service.get_overview(db, institution_id=inst_id)
    return make_ok(InstitutionOverviewOut(**data))


@router.get("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def get_profile(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.get_profile(db, institution_id=inst_id)
    return make_ok(InstitutionProfileOut.model_validate(inst))


@router.patch("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def update_profile(body: InstitutionProfileUpdate, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.update_profile(
        db, institution_id=inst_id,
        name=body.name, contact_phone=body.contact_phone, address=body.address,
    )
    await db.commit()
    await db.refresh(inst)
    return make_ok(InstitutionProfileOut.model_validate(inst))
