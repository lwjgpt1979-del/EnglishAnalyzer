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

from app.models.d4_knowledge import StudentKpMastery

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
