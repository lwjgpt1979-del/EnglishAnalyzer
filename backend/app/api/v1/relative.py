"""亲人端 API（D-076 / P0 亲人端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.relative import (
    BindRelativeRequest,
    BoundStudentOut,
    RelativeInviteCodeOut,
    StudentRelativeOut,
)
from app.services import relative_service

router = APIRouter(prefix="/relative", tags=["relative"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/invite-code", response_model=BaseResponse[RelativeInviteCodeOut])
async def generate_relative_invite_code(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    return make_ok(RelativeInviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.post("/bind", response_model=BaseResponse[StudentRelativeOut])
async def bind_as_relative(body: BindRelativeRequest, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    sr = await relative_service.bind_relative(
        db, relative_user=current_user, code=body.code.upper(), relationship=body.relationship,
    )
    await db.commit()
    return make_ok(StudentRelativeOut(
        id=sr.id, student_id=sr.student_id, relative_id=sr.relative_id,
        relationship=sr.relationship, is_active=sr.is_active, bound_at=sr.bound_at,
    ))


@router.get("/students", response_model=BaseResponse[list[BoundStudentOut]])
async def list_my_students(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    items = await relative_service.get_my_students(db, relative_id=current_user.id)
    return make_ok([
        BoundStudentOut(student_id=sr.student_id, relationship=sr.relationship, bound_at=sr.bound_at)
        for sr in items
    ])


@router.get("/my-relatives", response_model=BaseResponse[list[BoundStudentOut]])
async def list_my_relatives(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    items = await relative_service.get_my_relatives(db, student_id=current_user.id)
    return make_ok([
        BoundStudentOut(student_id=sr.relative_id, relationship=sr.relationship, bound_at=sr.bound_at)
        for sr in items
    ])


@router.delete("/relatives/{relative_id}", response_model=BaseResponse[dict])
async def unbind_my_relative(relative_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    await relative_service.unbind_relative(
        db, student_id=current_user.id, relative_id=relative_id,
    )
    await db.commit()
    return make_ok({"unbound": True})
