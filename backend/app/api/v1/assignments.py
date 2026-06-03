"""学生端老师作业 API（D-113 / Module 5B-S）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.assignment import (
    AssignmentOut, StudentAssignmentDetail, StudentAssignmentItem, SubmitIn,
)
from app.schemas.base import BaseResponse, make_ok
from app.services import assignment_service

router = APIRouter(prefix="/assignments", tags=["assignments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


def _assignment_out(a) -> AssignmentOut:
    return AssignmentOut(
        id=a.id, class_id=a.class_id, title=a.title, questions=a.questions or [],
        due_at=a.due_at.isoformat() if a.due_at else None, status=str(a.status),
        published_at=a.published_at.isoformat() if a.published_at else None,
        created_at=a.created_at.isoformat(),
    )


@router.get("", response_model=BaseResponse[list[StudentAssignmentItem]])
async def list_received_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    rows = await assignment_service.list_received(db, student_id=current_user.id)
    return make_ok([
        StudentAssignmentItem(
            id=a.id, title=a.title, status=str(a.status),
            due_at=a.due_at.isoformat() if a.due_at else None,
            submitted=sub is not None,
            score=float(sub.score) if (sub and sub.score is not None) else None,
        )
        for a, sub in rows
    ])


@router.get("/{assignment_id}", response_model=BaseResponse[StudentAssignmentDetail])
async def get_assignment_api(assignment_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    a, sub = await assignment_service.get_for_student(
        db, student_id=current_user.id, assignment_id=assignment_id)
    return make_ok(StudentAssignmentDetail(
        assignment=_assignment_out(a),
        submitted=sub is not None,
        answers=sub.answers if sub else None,
        score=float(sub.score) if (sub and sub.score is not None) else None,
    ))


@router.post("/{assignment_id}/submit", response_model=BaseResponse[dict])
async def submit_assignment_api(assignment_id: uuid.UUID, body: SubmitIn, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    sub = await assignment_service.submit_assignment(
        db, student_id=current_user.id, assignment_id=assignment_id, answers=body.answers)
    await db.commit()
    return make_ok({"id": str(sub.id), "submitted_at": sub.submitted_at.isoformat()})
