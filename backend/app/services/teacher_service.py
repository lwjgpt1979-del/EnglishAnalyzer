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


async def assert_bound(
    db: AsyncSession, *, teacher_id: uuid.UUID, student_id: uuid.UUID,
) -> None:
    """校验师生绑定关系，无则 403。"""
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权查看该学生数据")


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
    # —— 发"老师批注"通知给学生（D-074 Module 7B）——
    from app.services.notification_service import emit_teacher_comment
    try:
        await emit_teacher_comment(db, user_id=wq.student_id, wq_id=wq.id, teacher_id=teacher_id)
    except Exception:
        pass  # 通知失败不影响主链路
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


async def get_comments_for_wq_authorized(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
    caller_id: uuid.UUID,
) -> list[TeacherComment]:
    """查询某道错题所有批注（按创建时间升序）。

    仅允许：该错题所属学生 本人，或 与该学生有活跃绑定关系的教师。
    其他用户返回空列表（不报错，前端容错更友好）。
    """
    # 查 WQ 的归属学生
    wq_result = await db.execute(
        select(WrongQuestion).where(WrongQuestion.id == wq_id)
    )
    wq = wq_result.scalar_one_or_none()
    if wq is None:
        return []

    # 学生本人可读
    if wq.student_id == caller_id:
        return await get_comments_for_wq(db, wq_id=wq_id)

    # 绑定该学生的老师可读
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == caller_id,
            TeacherStudent.student_id == wq.student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is not None:
        return await get_comments_for_wq(db, wq_id=wq_id)

    # 其他用户返回空列表
    return []


# ─── cert 流程 + gate（D-075 / P0 老师端）────────────────────────────────────
async def submit_cert(
    db: AsyncSession,
    *,
    teacher: Teacher,
    cert_doc_url: str,
) -> Teacher:
    """老师提交认证材料。auto_approve=True 直接 certified；否则 pending。"""
    import datetime as _dt
    from app.core.config import settings
    teacher.cert_doc_url = cert_doc_url
    teacher.cert_submitted_at = _dt.datetime.now(_dt.timezone.utc)
    teacher.cert_reject_reason = None      # 重新提交清空上次驳回原因
    teacher.cert_claimed_by = None         # 重新进入队列
    teacher.cert_claimed_at = None
    if settings.auto_approve_teacher_cert:
        teacher.cert_status = "certified"  # type: ignore[assignment]
    else:
        teacher.cert_status = "pending"  # type: ignore[assignment]
    await db.flush()
    return teacher


async def claim_cert(db: AsyncSession, *, teacher_id: uuid.UUID,
                     admin_id: uuid.UUID) -> Teacher:
    """审核员认领认证任务（防多人同审，§5.8 Step1）。"""
    import datetime as _dt
    r = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = r.scalar_one_or_none()
    if teacher is None:
        raise AppError(code=404, message="老师不存在")
    if str(teacher.cert_status) != "pending":
        raise AppError(code=400, message="该申请非待审核状态，无法认领")
    if teacher.cert_claimed_by and teacher.cert_claimed_by != admin_id:
        raise AppError(code=409, message="该申请已被其他审核员认领")
    teacher.cert_claimed_by = admin_id
    teacher.cert_claimed_at = _dt.datetime.now(_dt.timezone.utc)
    await db.flush()
    return teacher


async def review_cert(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    approve: bool,
    reason: str | None = None,
) -> Teacher:
    """admin 审核老师认证。驳回必须填原因；通过/驳回均通知老师（§5.8 Step3）。"""
    import datetime as _dt
    r = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = r.scalar_one_or_none()
    if teacher is None:
        raise AppError(code=404, message="老师不存在")
    if not approve and not (reason or "").strip():
        raise AppError(code=400, message="驳回必须填写原因")
    teacher.cert_status = ("certified" if approve else "rejected")  # type: ignore[assignment]
    teacher.cert_reject_reason = None if approve else reason.strip()
    teacher.cert_reviewed_at = _dt.datetime.now(_dt.timezone.utc)
    await db.flush()
    # 通知老师
    from app.services import notification_service
    if approve:
        await notification_service.emit(
            db, user_id=teacher_id, type_="system", title="教师认证已通过",
            content="您的教师认证已通过审核，已获得「认证老师」标识。")
    else:
        await notification_service.emit(
            db, user_id=teacher_id, type_="system", title="教师认证未通过",
            content=f"驳回原因：{teacher.cert_reject_reason}。您可补充材料后重新提交。")
    return teacher


async def cert_quality(db: AsyncSession, *, days: int = 30) -> dict:
    """认证审核质量监控（§5.8）：近 N 天申请量 / 通过率 / 驳回原因 Top5。"""
    import datetime as _dt
    from sqlalchemy import func as _f
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    applied = int(await db.scalar(
        select(_f.count()).select_from(Teacher).where(
            Teacher.cert_submitted_at.isnot(None),
            Teacher.cert_submitted_at >= since)) or 0)
    reviewed = int(await db.scalar(
        select(_f.count()).select_from(Teacher).where(
            Teacher.cert_reviewed_at.isnot(None),
            Teacher.cert_reviewed_at >= since)) or 0)
    certified = int(await db.scalar(
        select(_f.count()).select_from(Teacher).where(
            Teacher.cert_reviewed_at.isnot(None),
            Teacher.cert_reviewed_at >= since,
            Teacher.cert_status == "certified")) or 0)
    pending = int(await db.scalar(
        select(_f.count()).select_from(Teacher).where(Teacher.cert_status == "pending")) or 0)
    reason_rows = (await db.execute(
        select(Teacher.cert_reject_reason, _f.count())
        .where(Teacher.cert_status == "rejected",
               Teacher.cert_reviewed_at >= since,
               Teacher.cert_reject_reason.isnot(None))
        .group_by(Teacher.cert_reject_reason)
        .order_by(_f.count().desc()).limit(5))).all()
    return {
        "days": days, "applied": applied, "reviewed": reviewed,
        "certified": certified, "pending": pending,
        "pass_rate_pct": round(certified / reviewed * 100, 1) if reviewed else 0.0,
        "reject_reasons_top": [{"reason": r, "count": int(c)} for r, c in reason_rows],
    }


def ensure_certified(teacher: Teacher | None) -> None:
    """权限 gate：未认证（uncertified/pending/rejected）禁止教师写操作。"""
    if teacher is None or str(teacher.cert_status) != "certified":
        raise AppError(code=403, message="老师认证未通过，无法执行此操作")


async def get_student_diagnosis_report(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
):
    """老师查指定学生的学情报告。需绑定关系；cert gate 由 endpoint 层做。"""
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权查看该学生数据")
    from app.services.diagnosis_service import get_diagnosis_report
    return await get_diagnosis_report(db, student_id=student_id)


async def join_institution(
    db: AsyncSession, *, teacher_user_id: uuid.UUID, code: str
) -> Teacher:
    """老师输 institution_join 邀请码加入机构（D-121）。"""
    now = datetime.now(timezone.utc)
    invite = (await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.type == "institution_join",
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
    )).scalar_one_or_none()
    if invite is None:
        raise AppError(code=400, message="邀请码无效或已过期")

    issuer = await db.get(User, invite.issuer_id)
    if issuer is None or issuer.institution_id is None:
        raise AppError(code=400, message="邀请码所属机构无效")

    teacher = await db.get(Teacher, teacher_user_id)
    if teacher is None:
        raise AppError(code=404, message="老师档案不存在")
    if teacher.institution_id is not None:
        raise AppError(code=409, message="您已加入机构，不能重复加入")

    teacher.institution_id = issuer.institution_id
    invite.used_at = now
    invite.target_id = teacher_user_id
    await db.flush()
    return teacher


async def list_teachers_for_admin(
    db: AsyncSession,
    *,
    cert_status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[tuple[Teacher, User]], int]:
    """平台管理员查看所有老师列表，可按 cert_status 筛选。"""
    from sqlalchemy import func
    base_conds = []
    if cert_status:
        base_conds.append(Teacher.cert_status == cert_status)

    total: int = (await db.execute(
        select(func.count())
        .select_from(Teacher)
        .where(*base_conds)
    )).scalar_one()

    rows = (await db.execute(
        select(Teacher, User)
        .join(User, User.id == Teacher.id)
        .where(*base_conds)
        .order_by(Teacher.id)
        .offset(skip)
        .limit(limit)
    )).all()

    return [(t, u) for t, u in rows], total
