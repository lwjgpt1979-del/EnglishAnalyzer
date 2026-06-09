"""个人知识点掌握台账服务（M39）。

所有写入通过 upsert_mastery 完成，调用方负责 commit。
查询通过 get_mastery_tree，按正确率升序返回（弱项在前）。

来源标识符约定：
  'practice'      — 自适应练习（AI 生成题）
  'paper_upload'  — 学生上传整卷
  'assignment'    — 教师布置作业
  'wrong_question'— 错题 AI 分析
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import StudentKpMastery, KpMasterySnapshot

# 合法来源标识符
KpSource = Literal["practice", "paper_upload", "assignment", "wrong_question"]


async def upsert_mastery(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_key: str,
    kp_id: uuid.UUID | None,
    is_correct: bool,
    source: KpSource,
    kp_description: str | None = None,
) -> None:
    """UPSERT 一次答题结果到个人知识点台账。

    - 原子性累加 correct_count / wrong_count（PostgreSQL ON CONFLICT DO UPDATE）
    - source 合并到 sources 数组（PostgreSQL array_append + DISTINCT，去重）
    - kp_description 仅首次写入（已有值则保留）
    - 不 commit，由调用方负责
    """
    delta_correct = 1 if is_correct else 0
    delta_wrong = 0 if is_correct else 1
    now = datetime.now(timezone.utc)

    stmt = pg_insert(StudentKpMastery).values(
        student_id=student_id,
        kp_key=kp_key,
        kp_id=kp_id,
        correct_count=delta_correct,
        wrong_count=delta_wrong,
        sources=[source],
        kp_description=kp_description,
        last_activity_at=now,
    ).on_conflict_do_update(
        index_elements=["student_id", "kp_key"],
        set_={
            "correct_count": StudentKpMastery.correct_count + delta_correct,
            "wrong_count": StudentKpMastery.wrong_count + delta_wrong,
            # 合并来源：用 PostgreSQL array 去重（避免 Python 层竞态）
            "sources": text(
                "ARRAY(SELECT DISTINCT unnest(student_kp_mastery.sources || ARRAY[:src]))"
            ).bindparams(src=source),
            # kp_description 仅首次写入有值时填入，已有值保留
            "kp_description": text(
                "COALESCE(student_kp_mastery.kp_description, :desc)"
            ).bindparams(desc=kp_description),
            "last_activity_at": now,
            # kp_id 首次写入后固定，不覆盖
            "kp_id": StudentKpMastery.kp_id,
        },
    )
    await db.execute(stmt)

    # ── 日快照（M46）─────────────────────────────────────────────────────────
    # 读取更新后的台账行，写入/更新当天快照（每 UTC 日期最多一行）
    today = now.date()
    row = (await db.execute(
        select(StudentKpMastery).where(
            StudentKpMastery.student_id == student_id,
            StudentKpMastery.kp_key == kp_key,
        )
    )).scalar_one_or_none()

    if row is not None:
        total = row.correct_count + row.wrong_count
        snap_accuracy = row.correct_count / total if total > 0 else 0.0
        snap_stmt = pg_insert(KpMasterySnapshot).values(
            student_id=student_id,
            kp_key=kp_key,
            snapshot_date=today,
            accuracy=snap_accuracy,
            correct_count=row.correct_count,
            wrong_count=row.wrong_count,
            recorded_at=now,
        ).on_conflict_do_update(
            constraint="uq_kp_snapshot_student_kp_date",
            set_={
                "accuracy": snap_accuracy,
                "correct_count": row.correct_count,
                "wrong_count": row.wrong_count,
                "recorded_at": now,
            },
        )
        await db.execute(snap_stmt)


async def get_kp_trend(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_key: str,
    days: int = 30,
) -> list[dict]:
    """返回指定 KP 的历史趋势快照（最近 days 天，按日期 ASC）。

    返回格式：[{date: "YYYY-MM-DD", accuracy: float, correct_count: int, wrong_count: int}, ...]
    """
    from datetime import timedelta
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)

    rows = (await db.execute(
        select(KpMasterySnapshot)
        .where(
            KpMasterySnapshot.student_id == student_id,
            KpMasterySnapshot.kp_key == kp_key,
            KpMasterySnapshot.snapshot_date >= since,
        )
        .order_by(KpMasterySnapshot.snapshot_date.asc())
    )).scalars().all()

    return [
        {
            "date": str(r.snapshot_date),
            "accuracy": round(r.accuracy, 4),
            "correct_count": r.correct_count,
            "wrong_count": r.wrong_count,
        }
        for r in rows
    ]


async def get_mastery_tree_for_teacher(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
) -> list[StudentKpMastery]:
    """教师查学生 KP 台账，先鉴权（学生须绑定该教师）。

    未绑定 → 抛 AppError(403)。
    """
    from sqlalchemy import select as _sel
    from app.models.d1_users import TeacherStudent
    from app.core.exceptions import AppError

    rel = (await db.execute(
        _sel(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )).scalar_one_or_none()

    if rel is None:
        raise AppError(code=403, message="该学生未绑定到您，无法查看其知识点台账")

    return await get_mastery_tree(db, student_id=student_id)


async def get_class_kp_stats(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
) -> dict:
    """聚合班级 KP 统计数据。

    返回结构：
      class_id, class_name, student_count
      top_weak_kps       — 全班平均正确率最低的 KP（≤10 条），按 avg_accuracy ASC
        · kp_key, avg_accuracy, student_count（有记录人数）,
          weak_count（<60%人数）, mastered_count（≥80%人数）
      students_attention — 全班平均正确率最低的学生（≤5 条），按 avg_accuracy ASC
        · student_id, nickname, avg_accuracy, weak_kp_count, total_kp_count
    """
    from collections import defaultdict
    from app.models.d1_users import User as _U
    from app.models.d7_teacher import ClassStudent
    from app.core.exceptions import AppError
    from app.services.class_service import _get_owned_class

    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    # 获取班级所有学生 ID
    student_ids = list(
        (await db.execute(
            select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
        )).scalars().all()
    )

    if not student_ids:
        return {
            "class_id": str(class_id),
            "class_name": cls.name,
            "student_count": 0,
            "top_weak_kps": [],
            "students_attention": [],
        }

    # 批量查台账（一次 SQL，按 student_id IN）
    mastery_rows = list(
        (await db.execute(
            select(StudentKpMastery).where(
                StudentKpMastery.student_id.in_(student_ids),
                StudentKpMastery.last_activity_at.is_not(None),
            )
        )).scalars().all()
    )

    # 拿学生昵称
    nick_map: dict[str, str | None] = {
        str(row.id): row.nickname
        for row in (await db.execute(
            select(_U.id, _U.nickname).where(_U.id.in_(student_ids))
        )).all()
    }

    # ── 按 kp_key 聚合 ──────────────────────────────────────────────────
    kp_data: dict[str, list[float]] = defaultdict(list)  # kp_key → [accuracy, ...]
    for row in mastery_rows:
        total = row.correct_count + row.wrong_count
        if total == 0:
            continue
        acc = row.correct_count / total
        kp_data[row.kp_key].append(acc)

    top_weak_kps = []
    for kp_key, accs in kp_data.items():
        avg_acc = sum(accs) / len(accs)
        top_weak_kps.append({
            "kp_key": kp_key,
            "avg_accuracy": round(avg_acc, 4),
            "student_count": len(accs),
            "weak_count": sum(1 for a in accs if a < 0.6),
            "mastered_count": sum(1 for a in accs if a >= 0.8),
        })
    top_weak_kps.sort(key=lambda x: x["avg_accuracy"])
    top_weak_kps = top_weak_kps[:10]

    # ── 按 student_id 聚合 ──────────────────────────────────────────────
    stu_data: dict[str, list[float]] = defaultdict(list)
    for row in mastery_rows:
        total = row.correct_count + row.wrong_count
        if total == 0:
            continue
        acc = row.correct_count / total
        stu_data[str(row.student_id)].append(acc)

    students_attention = []
    for stu_id_str, accs in stu_data.items():
        avg_acc = sum(accs) / len(accs)
        weak_kp_count = sum(1 for a in accs if a < 0.6)
        students_attention.append({
            "student_id": stu_id_str,
            "nickname": nick_map.get(stu_id_str),
            "avg_accuracy": round(avg_acc, 4),
            "weak_kp_count": weak_kp_count,
            "total_kp_count": len(accs),
        })
    students_attention.sort(key=lambda x: x["avg_accuracy"])
    students_attention = students_attention[:5]

    return {
        "class_id": str(class_id),
        "class_name": cls.name,
        "student_count": len(student_ids),
        "top_weak_kps": top_weak_kps,
        "students_attention": students_attention,
    }


async def get_mastery_tree(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> list[StudentKpMastery]:
    """返回当前学生的知识点树，按正确率升序（弱项在前）。

    正确率 = correct_count / (correct_count + wrong_count)，total=0 时视为 0。
    """
    rows = await db.execute(
        select(StudentKpMastery)
        .where(StudentKpMastery.student_id == student_id)
        .order_by(
            text(
                "CASE WHEN correct_count + wrong_count = 0 THEN 0.0 "
                "ELSE correct_count::float / (correct_count + wrong_count) END ASC"
            ),
            StudentKpMastery.last_activity_at.desc(),
        )
    )
    return list(rows.scalars().all())
