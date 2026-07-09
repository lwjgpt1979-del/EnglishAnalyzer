"""机构后台 service（D-120）：机构资料 + 数据概览。

机构归属：老师走 teachers.institution_id，学生走 students.institution_id，
机构管理员走 users.institution_id（请求时以 current_user.institution_id 为隔离键）。
"""
from __future__ import annotations

import datetime as dt
import random
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution, InviteCode, Student, Teacher, User
from app.models.d2_payments import InstitutionPurchase, Membership
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d5_learning import StudyCheckin

_CODE_CHARS = string.ascii_uppercase + string.digits
_JOIN_CODE_TTL_HOURS = 24 * 7


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

    # —— D-126 增强指标 ——
    cutoff_30d = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    expiring_30d_count = (await db.execute(
        select(func.count(func.distinct(Membership.user_id))).where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
            Membership.expires_at.is_not(None),
            Membership.expires_at <= cutoff_30d,
        )
    )).scalar_one()

    tier_rows = (await db.execute(
        select(Membership.tier, func.count()).where(
            Membership.user_id.in_(student_ids),
            Membership.is_active.is_(True),
        ).group_by(Membership.tier)
    )).all()
    _tc = {str(t): c for t, c in tier_rows}
    tier_distribution = {k: _tc.get(k, 0) for k in ("basic", "pro", "promax")}

    month_start = dt.datetime.now(dt.timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    month_purchase_fen = (await db.execute(
        select(func.coalesce(func.sum(InstitutionPurchase.amount_fen), 0)).where(
            InstitutionPurchase.institution_id == institution_id,
            InstitutionPurchase.created_at >= month_start,
        )
    )).scalar_one()

    return {
        "teacher_count": teacher_count,
        "student_count": student_count,
        "member_count": member_count,
        "active_7d_count": active_7d_count,
        "expiring_30d_count": expiring_30d_count,
        "tier_distribution": tier_distribution,
        "month_purchase_fen": month_purchase_fen,
    }


async def generate_join_code(
    db: AsyncSession, *, institution_id: uuid.UUID, issuer_id: uuid.UUID
) -> InviteCode:
    """生成机构加入邀请码（institution_join，6 位，7 天有效）。"""
    async def _unique() -> str:
        for _ in range(10):
            code = "".join(random.choices(_CODE_CHARS, k=6))
            r = await db.execute(select(InviteCode).where(InviteCode.code == code))
            if r.scalar_one_or_none() is None:
                return code
        raise AppError(code=500, message="邀请码生成失败，请重试")

    invite = InviteCode(
        id=uuid.uuid4(),
        code=await _unique(),
        type="institution_join",  # type: ignore[arg-type]
        issuer_id=issuer_id,
        target_id=None,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=_JOIN_CODE_TTL_HOURS),
    )
    db.add(invite)
    await db.flush()
    return invite


async def list_teachers(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> list[tuple[Teacher, User]]:
    """名下老师列表（Teacher 行 + 对应 User 展示字段）。"""
    rows = (await db.execute(
        select(Teacher, User)
        .join(User, User.id == Teacher.id)
        .where(Teacher.institution_id == institution_id)
    )).all()
    return [(t, u) for t, u in rows]


async def remove_teacher(
    db: AsyncSession, *, institution_id: uuid.UUID, teacher_id: uuid.UUID
) -> None:
    """把老师移出机构（teachers.institution_id=None）；跨机构拒绝。"""
    t = (await db.execute(
        select(Teacher).where(
            Teacher.id == teacher_id, Teacher.institution_id == institution_id
        )
    )).scalar_one_or_none()
    if t is None:
        raise AppError(code=404, message="老师不存在或不属于本机构")
    t.institution_id = None
    await db.flush()


async def set_teacher_quota(
    db: AsyncSession, *, institution_id: uuid.UUID, teacher_id: uuid.UUID,
    monthly_paper_quota: int | None, monthly_grading_quota: int | None = None,
    set_grading: bool = False,
) -> Teacher:
    """设/清除老师机构池内子上限（None=随机构池共享）；跨机构拒绝。

    set_grading=True 时才写 monthly_grading_quota（区分"未传"与"显式清空 None"）。
    """
    t = (await db.execute(
        select(Teacher).where(
            Teacher.id == teacher_id, Teacher.institution_id == institution_id
        )
    )).scalar_one_or_none()
    if t is None:
        raise AppError(code=404, message="老师不存在或不属于本机构")
    t.monthly_paper_quota = monthly_paper_quota
    if set_grading:
        t.monthly_grading_quota = monthly_grading_quota
    await db.flush()
    return t


async def learning_center(db: AsyncSession, *, institution_id: uuid.UUID) -> dict:
    """机构学情数据中心（5B.4）：名下学生活跃率 / 打卡概览 / 薄弱知识点 Top。"""
    from app.models.d16_question_domain import StudentKp   # R8.1:掌握台账统一到 node
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d9_system import UserActivity

    student_ids = select(Student.id).where(Student.institution_id == institution_id)
    total = int((await db.execute(
        select(func.count()).select_from(Student)
        .where(Student.institution_id == institution_id))).scalar_one() or 0)

    today = dt.date.today()
    d30 = today - dt.timedelta(days=29)
    active_30d = int(await db.scalar(
        select(func.count(func.distinct(UserActivity.user_id))).where(
            UserActivity.user_id.in_(student_ids), UserActivity.active_date >= d30)) or 0)
    checkin_students = int(await db.scalar(
        select(func.count(func.distinct(StudyCheckin.student_id))).where(
            StudyCheckin.student_id.in_(student_ids), StudyCheckin.checkin_date >= d30)) or 0)
    checkins_30d = int(await db.scalar(
        select(func.count()).select_from(StudyCheckin).where(
            StudyCheckin.student_id.in_(student_ids), StudyCheckin.checkin_date >= d30)) or 0)

    # 薄弱知识点 Top10：正确率<0.6 且作答≥3，按涉及学生数排序(R8.1:读 student_kp 按 node)
    rate = (StudentKp.practice_count - StudentKp.wrong_count) * 1.0 / func.nullif(
        StudentKp.practice_count, 0)
    weak_rows = (await db.execute(
        select(KnowledgeNode.name, func.count(func.distinct(StudentKp.student_id)),
               func.max(KnowledgeNode.description))
        .join(KnowledgeNode, KnowledgeNode.id == StudentKp.node_id)
        .where(StudentKp.student_id.in_(student_ids),
               StudentKp.practice_count >= 3, rate < 0.6)
        .group_by(KnowledgeNode.name)
        .order_by(func.count(func.distinct(StudentKp.student_id)).desc()).limit(10))).all()
    weak_kp = [{"kp_key": k, "student_count": int(c or 0), "description": d} for k, c, d in weak_rows]

    return {
        "total_students": total,
        "active_30d": active_30d,
        "active_rate_pct": round(active_30d / total * 100, 1) if total else 0.0,
        "checkin_students_30d": checkin_students,
        "checkins_30d": checkins_30d,
        "weak_kp_top": weak_kp,
    }
