"""ProMax 学生自助出卷 API（功能模块 5C）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.self_exam import (
    SelfExamBrief,
    SelfExamOut,
    SelfExamQuota,
    SelfExamSubmitIn,
    SelfExamSubmitResult,
)
from app.services import self_exam_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/self-exam", tags=["self-exam"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


def _to_out(se) -> SelfExamOut:
    return SelfExamOut(
        id=se.id, status=str(se.status), time_limit_sec=se.time_limit_sec,
        weak_kps=se.weak_kps or [], questions=se.snapshot or [],
        total=se.total, correct_count=se.correct_count, accuracy=se.accuracy,
        created_at=se.created_at,
    )


def _to_brief(se) -> SelfExamBrief:
    return SelfExamBrief(
        id=se.id, status=str(se.status), total=se.total,
        correct_count=se.correct_count, accuracy=se.accuracy, created_at=se.created_at,
    )


@router.get("/quota", response_model=BaseResponse[SelfExamQuota])
async def get_quota(db: DbDep, current_user: UserDep):
    q = await self_exam_service.quota_status(db, student_id=current_user.id)
    return make_ok(SelfExamQuota(**q))


@router.post("/generate", response_model=BaseResponse[SelfExamOut])
async def generate(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    se = await self_exam_service.create_self_exam(db, student_id=current_user.id)
    await db.commit()
    return make_ok(_to_out(se))


@router.get("/history", response_model=BaseResponse[list[SelfExamBrief]])
async def history(db: DbDep, current_user: UserDep):
    rows = await self_exam_service.list_history(db, student_id=current_user.id)
    return make_ok([_to_brief(r) for r in rows])


@router.get("/{exam_id}", response_model=BaseResponse[SelfExamOut])
async def get_exam(exam_id: uuid.UUID, db: DbDep, current_user: UserDep):
    se = await self_exam_service.get_self_exam(db, exam_id=exam_id, student_id=current_user.id)
    return make_ok(_to_out(se))


@router.post("/{exam_id}/submit", response_model=BaseResponse[SelfExamSubmitResult])
async def submit(exam_id: uuid.UUID, body: SelfExamSubmitIn, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    se, result = await self_exam_service.submit_self_exam(
        db, exam_id=exam_id, student_id=current_user.id, answers=body.answers)
    await db.commit()
    return make_ok(SelfExamSubmitResult(result=result, exam=_to_brief(se)))
