"""机构管理员后台 API（D-120）。

鉴权：require_role("institution_admin")；所有查询以 current_user.institution_id
为隔离键，机构只能看自己的数据。
"""
from __future__ import annotations

import uuid
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
    InstitutionTeacherOut,
    InviteCodeOut,
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


# ─── 老师管理（D-121）──────────────────────────────────────────────────────

@router.post("/teachers/invite-code", response_model=BaseResponse[InviteCodeOut])
async def gen_teacher_invite_code(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    invite = await institution_service.generate_join_code(
        db, institution_id=inst_id, issuer_id=admin.id)
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.get("/teachers", response_model=BaseResponse[list[InstitutionTeacherOut]])
async def list_institution_teachers(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_service.list_teachers(db, institution_id=inst_id)
    return make_ok([
        InstitutionTeacherOut(
            id=t.id, nickname=u.nickname, phone=u.phone,
            subject=t.subject, cert_status=str(t.cert_status),
        ) for t, u in rows
    ])


@router.delete("/teachers/{teacher_id}", response_model=BaseResponse[dict])
async def remove_institution_teacher(teacher_id: uuid.UUID, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    await institution_service.remove_teacher(
        db, institution_id=inst_id, teacher_id=teacher_id)
    await db.commit()
    return make_ok({"removed": str(teacher_id)})
