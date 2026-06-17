"""R3 判掌握 + 回写(KP-First):作答落 answer_log + student_kp;原题+N仿真全对 → 判掌握。

- log_answer:每次作答 → answer_log(分区事件表)+ student_kp(node 维度投影:练习/错次/最近)。
- judge_and_mark:做对"原题 + N 道仿真"(N 可配)→ wrong_record 判掌握 + student_kp.mastery=1。
判掌握同步回写旧 student_kp_mastery 台账(兼容现有诊断/前台)。
"""
from __future__ import annotations

import datetime as _dt
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import (
    AnswerLog, StudentKp, PlatformQuestion, PlatformQuestionKp, WrongRecord,
)

DEFAULT_REQUIRED_SIMS = 3   # 原题 + N 仿真;N 可配(后台/settings 覆盖)


async def log_answer(
    db: AsyncSession, *, student_id: uuid.UUID, q_scope: str, question_id: uuid.UUID,
    node_id: uuid.UUID | None, is_correct: bool, feature: str | None = None,
) -> None:
    """记一次作答:answer_log 事件 + student_kp(node 投影)计数。"""
    db.add(AnswerLog(
        id=uuid.uuid4(), student_id=student_id, q_scope=q_scope,
        question_id=question_id, is_correct=is_correct, feature=feature,
    ))
    if node_id is not None:
        await db.execute(
            pg_insert(StudentKp)
            .values(
                student_id=student_id, node_id=node_id,
                practice_count=1, wrong_count=0 if is_correct else 1,
                last_practice_at=sa.func.now(), source_tags=["practice"], in_scope=True,
            )
            .on_conflict_do_update(
                index_elements=["student_id", "node_id"],
                set_={
                    "practice_count": StudentKp.practice_count + 1,
                    "wrong_count": StudentKp.wrong_count + (0 if is_correct else 1),
                    "last_practice_at": sa.func.now(),
                },
            )
        )
    await db.flush()


async def _correct_sim_count(db: AsyncSession, student_id: uuid.UUID, node_id: uuid.UUID) -> int:
    """该 student 在该 node 上**做对的不同仿真**数(从 answer_log 聚合)。"""
    return (await db.execute(
        sa.select(sa.func.count(sa.distinct(AnswerLog.question_id)))
        .select_from(AnswerLog)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == AnswerLog.question_id)
        .join(PlatformQuestion, PlatformQuestion.id == AnswerLog.question_id)
        .where(AnswerLog.student_id == student_id, AnswerLog.is_correct.is_(True),
               PlatformQuestionKp.node_id == node_id, PlatformQuestion.type == "sim")
    )).scalar_one()


async def _original_done_correct(db: AsyncSession, student_id: uuid.UUID, original_question_id: uuid.UUID) -> bool:
    return (await db.execute(
        sa.select(AnswerLog.id).where(
            AnswerLog.student_id == student_id,
            AnswerLog.question_id == original_question_id,
            AnswerLog.is_correct.is_(True),
        ).limit(1)
    )).first() is not None


async def judge_and_mark(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID,
    original_question_id: uuid.UUID, original_q_scope: str,
    required_sims: int = DEFAULT_REQUIRED_SIMS,
) -> bool:
    """原题做对 + 该 node 做对仿真 ≥ N → 判掌握:wrong_record.mastered + student_kp.mastery=1。

    返回是否判为掌握。
    """
    if not await _original_done_correct(db, student_id, original_question_id):
        return False
    if await _correct_sim_count(db, student_id, node_id) < required_sims:
        return False

    # 错题判掌握
    await db.execute(
        sa.update(WrongRecord)
        .where(WrongRecord.student_id == student_id,
               WrongRecord.q_scope == original_q_scope,
               WrongRecord.question_id == original_question_id)
        .values(status="mastered", mastered_at=sa.func.now(), mastery_source="auto")
    )
    # 回写 student_kp(node 维度)掌握度
    await db.execute(
        sa.update(StudentKp)
        .where(StudentKp.student_id == student_id, StudentKp.node_id == node_id)
        .values(mastery=1.0)
    )
    await db.flush()
    return True
