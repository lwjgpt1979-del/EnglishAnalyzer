"""老师出卷下发闭环 service（D-113 / Module 5B + 5B-S）。零迁移、无 LLM。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d7_teacher import Assignment, AssignmentSubmission, ClassStudent
from app.services import class_service, notification_service


# ─── 老师端 ──────────────────────────────────────────────────────────

async def _get_owned_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = (await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id, Assignment.teacher_id == teacher_id)
    )).scalar_one_or_none()
    if a is None:
        raise AppError(code=404, message="作业不存在或无权访问")
    return a


async def create_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID,
    title: str, questions: list, due_at: datetime | None = None,
) -> Assignment:
    await class_service._get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    a = Assignment(
        id=uuid.uuid4(), teacher_id=teacher_id, class_id=class_id,
        title=title, questions=questions, due_at=due_at, status="draft",
    )
    db.add(a)
    await db.flush()
    return a


async def publish_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    if str(a.status) == "closed":
        raise AppError(code=400, message="作业已关闭，无法发布")
    a.status = "published"
    if a.published_at is None:
        a.published_at = datetime.now(timezone.utc)
    await db.flush()
    # 下发站内通知给班级每个学生
    student_ids = (await db.execute(
        select(ClassStudent.student_id).where(ClassStudent.class_id == a.class_id)
    )).scalars().all()
    for sid in student_ids:
        await notification_service.emit(
            db, user_id=sid, type_="assignment",
            title="老师布置了新作业",
            content=f"《{a.title}》，请尽快完成。",
            meta={"assignment_id": str(a.id)},
        )
    return a


async def close_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    a.status = "closed"
    await db.flush()
    return a


async def list_teacher_assignments(
    db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID | None = None,
) -> list[tuple[Assignment, int]]:
    q = select(Assignment).where(Assignment.teacher_id == teacher_id)
    if class_id is not None:
        q = q.where(Assignment.class_id == class_id)
    rows = list((await db.execute(q.order_by(Assignment.created_at.desc()))).scalars().all())
    out: list[tuple[Assignment, int]] = []
    for a in rows:
        from sqlalchemy import func
        cnt = (await db.execute(
            select(func.count()).select_from(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == a.id)
        )).scalar_one()
        out.append((a, int(cnt)))
    return out


async def get_assignment_for_teacher(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> tuple[Assignment, list[AssignmentSubmission]]:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    subs = list((await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == a.id)
        .order_by(AssignmentSubmission.submitted_at)
    )).scalars().all())
    return a, subs


async def grade_submission(
    db: AsyncSession, *, teacher_id: uuid.UUID, submission_id: uuid.UUID, score: float,
) -> AssignmentSubmission:
    sub = (await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
    )).scalar_one_or_none()
    if sub is None:
        raise AppError(code=404, message="提交不存在")
    # 校验该提交所属作业归本老师
    await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=sub.assignment_id)
    sub.score = score
    await db.flush()
    return sub


# ─── 学生端 ──────────────────────────────────────────────────────────

async def _assert_in_class(db: AsyncSession, *, student_id: uuid.UUID, class_id: uuid.UUID) -> None:
    r = (await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id, ClassStudent.student_id == student_id)
    )).scalar_one_or_none()
    if r is None:
        raise AppError(code=403, message="你不在该班级，无法访问此作业")


async def _my_submission(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID,
) -> AssignmentSubmission | None:
    return (await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.student_id == student_id)
    )).scalar_one_or_none()


async def list_received(
    db: AsyncSession, *, student_id: uuid.UUID,
) -> list[tuple[Assignment, AssignmentSubmission | None]]:
    class_ids = (await db.execute(
        select(ClassStudent.class_id).where(ClassStudent.student_id == student_id)
    )).scalars().all()
    if not class_ids:
        return []
    rows = list((await db.execute(
        select(Assignment).where(
            Assignment.class_id.in_(class_ids), Assignment.status == "published")
        .order_by(Assignment.published_at.desc())
    )).scalars().all())
    out: list[tuple[Assignment, AssignmentSubmission | None]] = []
    for a in rows:
        sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
        out.append((a, sub))
    return out


async def get_for_student(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID,
) -> tuple[Assignment, AssignmentSubmission | None]:
    a = (await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )).scalar_one_or_none()
    if a is None or str(a.status) == "draft":
        raise AppError(code=404, message="作业不存在")
    await _assert_in_class(db, student_id=student_id, class_id=a.class_id)
    sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
    return a, sub


async def submit_assignment(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID, answers,
) -> AssignmentSubmission:
    a = (await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )).scalar_one_or_none()
    if a is None or str(a.status) != "published":
        raise AppError(code=400, message="作业不可提交")
    await _assert_in_class(db, student_id=student_id, class_id=a.class_id)
    if a.due_at is not None and datetime.now(timezone.utc) > a.due_at:
        raise AppError(code=400, message="作业已截止")
    sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
    now = datetime.now(timezone.utc)
    if sub is not None:
        sub.answers = answers
        sub.submitted_at = now
        await db.flush()
        return sub
    sub = AssignmentSubmission(
        id=uuid.uuid4(), assignment_id=a.id, student_id=student_id,
        answers=answers, submitted_at=now,
    )
    db.add(sub)
    await db.flush()
    return sub
