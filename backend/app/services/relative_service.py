"""亲人端业务逻辑（D-076 / P0 亲人端）。"""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import InviteCode, Relative, StudentRelative, User

_CODE_CHARS = string.ascii_uppercase + string.digits
_CODE_LENGTH = 6
_CODE_TTL_HOURS = 24
MAX_RELATIVES_PER_STUDENT = 4


async def generate_invite_code(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> InviteCode:
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
        type="relative_bind",  # type: ignore[arg-type]
        issuer_id=student_id,
        target_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=_CODE_TTL_HOURS),
    )
    db.add(invite)
    await db.flush()
    return invite


async def bind_relative(
    db: AsyncSession,
    *,
    relative_user: User,
    code: str,
    relationship: str,
) -> StudentRelative:
    now = datetime.now(timezone.utc)

    invite_r = await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.type == "relative_bind",
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
    )
    invite = invite_r.scalar_one_or_none()
    if invite is None:
        raise AppError(code=400, message="邀请码无效或已过期")

    student_id = invite.issuer_id

    if student_id == relative_user.id:
        raise AppError(code=400, message="不能绑定到自己")

    existing_r = await db.execute(
        select(StudentRelative).where(
            StudentRelative.student_id == student_id,
            StudentRelative.relative_id == relative_user.id,
            StudentRelative.is_active.is_(True),
        )
    )
    if existing_r.scalar_one_or_none() is not None:
        raise AppError(code=409, message="您已是该学生的家人")

    cnt_r = await db.execute(
        select(func.count(StudentRelative.id)).where(
            StudentRelative.student_id == student_id,
            StudentRelative.is_active.is_(True),
        )
    )
    if cnt_r.scalar_one() >= MAX_RELATIVES_PER_STUDENT:
        raise AppError(code=400, message=f"该学生已有 {MAX_RELATIVES_PER_STUDENT} 个家人，达到上限")

    rel_r = await db.execute(select(Relative).where(Relative.id == relative_user.id))
    if rel_r.scalar_one_or_none() is None:
        db.add(Relative(id=relative_user.id))

    relative_user.role = "relative"  # type: ignore[assignment]

    sr = StudentRelative(
        id=uuid.uuid4(),
        student_id=student_id,
        relative_id=relative_user.id,
        relationship=relationship,
        is_active=True,
        bound_at=now,
    )
    db.add(sr)
    invite.used_at = now
    await db.flush()
    return sr


async def get_my_students(
    db: AsyncSession,
    *,
    relative_id: uuid.UUID,
) -> list[StudentRelative]:
    r = await db.execute(
        select(StudentRelative).where(
            StudentRelative.relative_id == relative_id,
            StudentRelative.is_active.is_(True),
        ).order_by(StudentRelative.bound_at.desc())
    )
    return list(r.scalars().all())


async def get_my_relatives(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> list[StudentRelative]:
    r = await db.execute(
        select(StudentRelative).where(
            StudentRelative.student_id == student_id,
            StudentRelative.is_active.is_(True),
        ).order_by(StudentRelative.bound_at.desc())
    )
    return list(r.scalars().all())


async def unbind_relative(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    relative_id: uuid.UUID,
) -> None:
    r = await db.execute(
        select(StudentRelative).where(
            StudentRelative.student_id == student_id,
            StudentRelative.relative_id == relative_id,
            StudentRelative.is_active.is_(True),
        )
    )
    sr = r.scalar_one_or_none()
    if sr is None:
        raise AppError(code=404, message="未找到该亲人绑定关系")
    sr.is_active = False
    sr.unbound_at = datetime.now(timezone.utc)
    await db.flush()


async def assert_bound(
    db: AsyncSession,
    *,
    relative_id: uuid.UUID,
    student_id: uuid.UUID,
) -> None:
    r = await db.execute(
        select(StudentRelative).where(
            StudentRelative.student_id == student_id,
            StudentRelative.relative_id == relative_id,
            StudentRelative.is_active.is_(True),
        )
    )
    if r.scalar_one_or_none() is None:
        raise AppError(code=403, message="您不是该学生的家人")
