"""教师端业务逻辑。

功能：
- become_teacher: 学生升级为教师角色（幂等）
- generate_invite_code: 教师生成6位邀请码（有效24h）
- bind_with_teacher: 学生通过邀请码绑定教师
- get_my_students: 教师查看所有活跃绑定学生
- get_student_wrong_questions: 教师查看指定学生错题（含绑定校验）
- add_comment: 教师为错题添加批注（含绑定校验）
- get_comments_for_wq: 查询某错题所有批注（按时间升序）
"""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import InviteCode, Teacher, TeacherStudent, User
from app.models.d3_wrong_questions import TeacherComment, WrongQuestion
from app.schemas.teacher import BecomeTeacherRequest, TeacherCommentCreate

_CODE_CHARS = string.ascii_uppercase + string.digits  # A-Z 0-9, 36 chars
_CODE_LENGTH = 6
_CODE_TTL_HOURS = 24


async def become_teacher(
    db: AsyncSession,
    *,
    user: User,
    data: BecomeTeacherRequest,
) -> Teacher:
    """将当前用户升级为教师角色，创建 Teacher 扩展记录。已是教师则幂等返回。"""
    result = await db.execute(select(Teacher).where(Teacher.id == user.id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    user.role = "teacher"  # type: ignore[assignment]
    teacher = Teacher(
        id=user.id,
        subject=data.subject,
        cert_status="uncertified",  # type: ignore[arg-type]
        max_students=50,
    )
    db.add(teacher)
    await db.flush()
    return teacher


async def generate_invite_code(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
) -> InviteCode:
    """生成6位大写字母+数字邀请码，有效期24小时，冲突重试10次。"""

    async def _unique_code() -> str:
        for _ in range(10):
            code = "".join(random.choices(_CODE_CHARS, k=_CODE_LENGTH))
            r = await db.execute(select(InviteCode).where(InviteCode.code == code))
            if r.scalar_one_or_none() is None:
                return code
        raise AppError(code=500, message="邀请码生成失败，请重试")

    code = await _unique_code()
    invite = InviteCode(
        id=uuid.uuid4(),
        code=code,
        type="teacher_bind",  # type: ignore[arg-type]
        issuer_id=teacher_id,
        target_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=_CODE_TTL_HOURS),
    )
    db.add(invite)
    await db.flush()
    return invite


async def bind_with_teacher(
    db: AsyncSession,
    *,
    student: User,
    code: str,
) -> TeacherStudent:
    """学生通过邀请码绑定老师。

    - 码无效/已过期/已使用 → AppError(400)
    - 已绑定该老师 → AppError(409)
    """
    now = datetime.now(timezone.utc)

    invite_result = await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.type == "teacher_bind",
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise AppError(code=400, message="邀请码无效或已过期")

    teacher_id = invite.issuer_id

    existing = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student.id,
            TeacherStudent.status == "active",
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError(code=409, message="您已绑定该老师")

    relation = TeacherStudent(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        student_id=student.id,
        bind_type="self_bound",  # type: ignore[arg-type]
        bind_source="miniprogram_link",  # type: ignore[arg-type]
        status="active",  # type: ignore[arg-type]
        requested_at=now,
        bound_at=now,
    )
    db.add(relation)
    invite.used_at = now
    await db.flush()
    return relation


async def get_my_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
) -> list[TeacherStudent]:
    """返回教师所有活跃绑定学生。"""
    result = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.status == "active",
        )
    )
    return list(result.scalars().all())


async def get_student_wrong_questions(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
) -> list[WrongQuestion]:
    """教师查看指定学生的错题列表，先校验绑定关系。"""
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权查看该学生数据")

    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.student_id == student_id)
        .order_by(WrongQuestion.created_at.desc())
    )
    return list(result.scalars().all())


async def add_comment(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    wq_id: uuid.UUID,
    data: TeacherCommentCreate,
) -> TeacherComment:
    """教师为错题添加批注，先校验该错题归属学生是否为教师的绑定学生。"""
    wq_result = await db.execute(
        select(WrongQuestion).where(WrongQuestion.id == wq_id)
    )
    wq = wq_result.scalar_one_or_none()
    if wq is None:
        raise AppError(code=404, message="错题不存在")

    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == wq.student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权批注该学生的错题")

    comment = TeacherComment(
        id=uuid.uuid4(),
        wrong_question_id=wq_id,
        teacher_id=teacher_id,
        comment_text=data.comment_text,
    )
    db.add(comment)
    await db.flush()
    return comment


async def get_comments_for_wq(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
) -> list[TeacherComment]:
    """查询某道错题所有批注（按创建时间升序）。"""
    result = await db.execute(
        select(TeacherComment)
        .where(TeacherComment.wrong_question_id == wq_id)
        .order_by(TeacherComment.created_at.asc())
    )
    return list(result.scalars().all())
