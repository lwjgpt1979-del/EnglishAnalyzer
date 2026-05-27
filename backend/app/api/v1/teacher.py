"""教师端 API。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.teacher import (
    BecomeTeacherRequest,
    BindTeacherRequest,
    InviteCodeOut,
    TeacherCommentCreate,
    TeacherCommentOut,
    TeacherProfileOut,
    TeacherStudentOut,
)
from app.schemas.wrong_questions import WrongQuestionOut
from app.services import teacher_service

router = APIRouter(prefix="/teacher", tags=["teacher"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/profile", response_model=BaseResponse[TeacherProfileOut])
async def become_teacher(
    body: BecomeTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """任意用户升级为教师角色（幂等）。"""
    await get_rls_db(db, str(current_user.id))
    teacher = await teacher_service.become_teacher(db, user=current_user, data=body)
    await db.commit()
    return make_ok(
        TeacherProfileOut(
            user_id=teacher.id,
            subject=teacher.subject,
            cert_status=str(teacher.cert_status),
            max_students=teacher.max_students,
        )
    )


@router.post("/invite-code", response_model=BaseResponse[InviteCodeOut])
async def create_invite_code(db: DbDep, current_user: UserDep):
    """教师生成邀请码（有效期24小时）。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可生成邀请码")
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(
        db, teacher_id=current_user.id
    )
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.post("/bind", response_model=BaseResponse[TeacherStudentOut])
async def bind_teacher(
    body: BindTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """学生通过邀请码绑定老师。"""
    await get_rls_db(db, str(current_user.id))
    relation = await teacher_service.bind_with_teacher(
        db, student=current_user, code=body.code.upper()
    )
    await db.commit()
    return make_ok(
        TeacherStudentOut(
            student_id=relation.student_id,
            bound_at=relation.bound_at,
        )
    )


@router.get("/students", response_model=BaseResponse[list[TeacherStudentOut]])
async def list_my_students(db: DbDep, current_user: UserDep):
    """教师查看所有绑定学生。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生列表")
    await get_rls_db(db, str(current_user.id))
    students = await teacher_service.get_my_students(
        db, teacher_id=current_user.id
    )
    return make_ok(
        [TeacherStudentOut(student_id=s.student_id, bound_at=s.bound_at) for s in students]
    )


@router.get(
    "/students/{student_id}/wrong-questions",
    response_model=BaseResponse[list[WrongQuestionOut]],
)
async def get_student_wrong_questions(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """教师查看指定绑定学生的错题列表。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生错题")
    await get_rls_db(db, str(current_user.id))
    wqs = await teacher_service.get_student_wrong_questions(
        db, teacher_id=current_user.id, student_id=student_id
    )
    return make_ok([WrongQuestionOut.model_validate(wq) for wq in wqs])


@router.post(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[TeacherCommentOut],
)
async def add_comment(
    wq_id: uuid.UUID,
    body: TeacherCommentCreate,
    db: DbDep,
    current_user: UserDep,
):
    """教师为错题添加批注。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可添加批注")
    await get_rls_db(db, str(current_user.id))
    comment = await teacher_service.add_comment(
        db, teacher_id=current_user.id, wq_id=wq_id, data=body
    )
    await db.commit()
    return make_ok(TeacherCommentOut.model_validate(comment))


@router.get(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[list[TeacherCommentOut]],
)
async def get_comments(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查看错题上的所有老师批注。

    学生（WQ 所有者）和绑定该学生的老师均可访问。
    未授权则返回空列表（不报错，前端容错更友好）。
    """
    await get_rls_db(db, str(current_user.id))
    comments = await teacher_service.get_comments_for_wq_authorized(
        db, wq_id=wq_id, caller_id=current_user.id
    )
    return make_ok([TeacherCommentOut.model_validate(c) for c in comments])
