"""班级管理（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import TeacherStudent
from app.models.d7_teacher import Class, ClassStudent


async def create_class(db: AsyncSession, *, teacher_id: uuid.UUID, name: str) -> Class:
    cls = Class(id=uuid.uuid4(), teacher_id=teacher_id, name=name)
    db.add(cls)
    await db.flush()
    return cls


async def list_classes(db: AsyncSession, *, teacher_id: uuid.UUID) -> list[tuple[Class, int]]:
    r = await db.execute(
        select(Class).where(Class.teacher_id == teacher_id).order_by(Class.created_at.desc())
    )
    classes = list(r.scalars().all())
    out: list[tuple[Class, int]] = []
    for c in classes:
        cnt_r = await db.execute(
            select(func.count(ClassStudent.student_id)).where(ClassStudent.class_id == c.id)
        )
        out.append((c, cnt_r.scalar_one()))
    return out


async def _get_owned_class(db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID) -> Class:
    r = await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher_id)
    )
    cls = r.scalar_one_or_none()
    if cls is None:
        raise AppError(code=404, message="班级不存在或无权访问")
    return cls


async def delete_class(db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID) -> None:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    await db.execute(delete(ClassStudent).where(ClassStudent.class_id == cls.id))
    await db.delete(cls)
    await db.flush()


async def add_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
    student_ids: list[uuid.UUID],
) -> int:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    bound_r = await db.execute(
        select(TeacherStudent.student_id).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.status == "active",
            TeacherStudent.student_id.in_(student_ids),
        )
    )
    bound_set = {row[0] for row in bound_r.all()}
    invalid = set(student_ids) - bound_set
    if invalid:
        raise AppError(code=400, message=f"以下学生未绑定到该老师：{list(invalid)}")

    existing_r = await db.execute(
        select(ClassStudent.student_id).where(
            ClassStudent.class_id == cls.id,
            ClassStudent.student_id.in_(student_ids),
        )
    )
    existing_set = {row[0] for row in existing_r.all()}

    now = datetime.now(timezone.utc)
    added = 0
    for sid in student_ids:
        if sid in existing_set:
            continue
        db.add(ClassStudent(class_id=cls.id, student_id=sid, joined_at=now))
        added += 1
    await db.flush()
    return added


async def remove_student(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
    student_id: uuid.UUID,
) -> None:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    r = await db.execute(
        delete(ClassStudent).where(
            ClassStudent.class_id == cls.id,
            ClassStudent.student_id == student_id,
        )
    )
    if (r.rowcount or 0) == 0:
        raise AppError(code=404, message="该学生不在班级中")
    await db.flush()


async def list_class_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
) -> list[ClassStudent]:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    r = await db.execute(
        select(ClassStudent).where(ClassStudent.class_id == cls.id)
        .order_by(ClassStudent.joined_at.desc())
    )
    return list(r.scalars().all())


from collections import Counter


async def build_class_report(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
) -> dict:
    """聚合全班学生的 diagnosis 数据。MVP 班级规模 < 50 内存聚合可接受。"""
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    cs_r = await db.execute(
        select(ClassStudent.student_id).where(ClassStudent.class_id == cls.id)
    )
    student_ids = [row[0] for row in cs_r.all()]

    from app.services.diagnosis_service import get_diagnosis_report
    err_counter: Counter = Counter()
    kp_counter: Counter = Counter()
    total_questions = 0
    rates: list[float] = []
    rankings: list[dict] = []

    # Prefetch student nicknames
    from app.models.d1_users import User as _U
    nick_rows = (await db.execute(
        select(_U.id, _U.nickname).where(_U.id.in_(student_ids))
    )).all() if student_ids else []
    nick_map = {str(r[0]): r[1] for r in nick_rows}

    for sid in student_ids:
        report = await get_diagnosis_report(db, student_id=sid)
        total_questions += report.total_questions
        rates.append(report.mastery_rate)
        rankings.append({
            "student_id": sid,
            "total_questions": report.total_questions,
            "mastery_rate": report.mastery_rate,
            "nickname": nick_map.get(str(sid)),
        })
        for et in report.top_error_types:
            err_counter[et.error_type] += et.count
        for kp in report.top_weak_knowledge_points:
            kp_counter[kp.knowledge_point] += kp.count

    avg_rate = (sum(rates) / len(rates)) if rates else 0.0
    rankings.sort(key=lambda x: x["mastery_rate"], reverse=True)

    return {
        "class_id": cls.id,
        "class_name": cls.name,
        "student_count": len(student_ids),
        "avg_mastery_rate": round(avg_rate, 4),
        "total_questions": total_questions,
        "top_error_types": [{"type": t, "count": c} for t, c in err_counter.most_common(10)],
        "top_weak_knowledge_points": [{"kp": k, "count": c} for k, c in kp_counter.most_common(10)],
        "students_ranking": rankings,
    }
