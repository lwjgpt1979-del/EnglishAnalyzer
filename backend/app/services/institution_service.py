"""机构后台 service（D-120）：机构资料 + 数据概览。

机构归属：老师走 teachers.institution_id，学生走 students.institution_id，
机构管理员走 users.institution_id（请求时以 current_user.institution_id 为隔离键）。
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution, Student, Teacher
from app.models.d2_payments import Membership
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d5_learning import StudyCheckin


async def get_profile(db: AsyncSession, *, institution_id: uuid.UUID) -> Institution:
    inst = (await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )).scalar_one_or_none()
    if inst is None:
        raise AppError(code=404, message="机构不存在")
    return inst


async def update_profile(
    db: AsyncSession, *, institution_id: uuid.UUID,
    name: str | None = None, contact_phone: str | None = None,
    address: str | None = None,
) -> Institution:
    inst = await get_profile(db, institution_id=institution_id)
    if name is not None:
        inst.name = name
    if contact_phone is not None:
        inst.contact_phone = contact_phone
    if address is not None:
        inst.address = address
    await db.flush()
    return inst


async def get_overview(db: AsyncSession, *, institution_id: uuid.UUID) -> dict:
    teacher_count = (await db.execute(
        select(func.count()).select_from(Teacher)
        .where(Teacher.institution_id == institution_id)
    )).scalar_one()

    student_count = (await db.execute(
        select(func.count()).select_from(Student)
        .where(Student.institution_id == institution_id)
    )).scalar_one()

    # 名下学生 id 子查询
    student_ids = select(Student.id).where(Student.institution_id == institution_id)

    member_count = (await db.execute(
        select(func.count(func.distinct(Membership.user_id))).where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
            Membership.tier != "free",
        )
    )).scalar_one()

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    since_date = since.date()
    active_checkin = select(StudyCheckin.student_id.label("student_id")).where(
        StudyCheckin.student_id.in_(student_ids),
        StudyCheckin.checkin_date >= since_date,
    )
    active_wq = select(WrongQuestion.student_id.label("student_id")).where(
        WrongQuestion.student_id.in_(student_ids),
        WrongQuestion.created_at >= since,
    )
    active_ids = active_checkin.union(active_wq).subquery()
    active_7d_count = (await db.execute(
        select(func.count(func.distinct(active_ids.c.student_id)))
    )).scalar_one()

    return {
        "teacher_count": teacher_count,
        "student_count": student_count,
        "member_count": member_count,
        "active_7d_count": active_7d_count,
    }
