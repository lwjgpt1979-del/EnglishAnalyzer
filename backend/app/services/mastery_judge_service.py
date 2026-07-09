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

# ── BKT(贝叶斯知识追踪):掌握度=概率,随每次作答升降,建模蒙对/手滑 ──────────
BKT_L0 = 0.25        # 初始掌握先验 P(L0)
BKT_T = 0.18         # 学得率 P(T):每次作答机会转化为掌握的概率
BKT_G = 0.20         # 蒙对率 P(G):未掌握却答对
BKT_S = 0.10         # 手滑率 P(S):已掌握却答错
BKT_MASTERED = 0.95  # 判掌握阈值(需连续答对才能跨过,抗运气过关)


def bkt_update(prior: float | None, correct: bool) -> float:
    """一次作答后的 BKT 掌握度更新:先按证据求后验,再叠加学得转移。返回新的 P(掌握)∈[0,1]。
    prior=None 用初始先验 L0。连续答对快速逼近 1;答错按手滑率回拉。"""
    p = BKT_L0 if prior is None else min(max(float(prior), 0.0), 1.0)
    if correct:
        num = p * (1 - BKT_S)
        den = num + (1 - p) * BKT_G
    else:
        num = p * BKT_S
        den = num + (1 - p) * (1 - BKT_G)
    post = (num / den) if den > 0 else p
    return round(post + (1 - post) * BKT_T, 4)   # 习得转移


async def log_answer(
    db: AsyncSession, *, student_id: uuid.UUID, q_scope: str, question_id: uuid.UUID,
    node_id: uuid.UUID | None, is_correct: bool, feature: str | None = None,
) -> None:
    """记一次作答:answer_log 事件 + student_kp(node 投影)计数。

    加权掌握度(m139):首答(feature!='review' 且此前无该题作答)→ 计 fa_correct/fa_wrong;
    订正/复习(feature='review')不计首答,其订正对/错由 wrong_review_service 记 corrected_count/
    redo_wrong_count。原 practice_count/wrong_count 仍按每次作答累加(总次数,供既有正确率)。
    """
    # 首答判定要在写入本条 answer_log 之前查(避免把自己算进历史)
    is_first = feature != "review" and (await db.execute(
        sa.select(AnswerLog.id).where(
            AnswerLog.student_id == student_id,
            AnswerLog.question_id == question_id,
        ).limit(1)
    )).first() is None
    db.add(AnswerLog(
        id=uuid.uuid4(), student_id=student_id, q_scope=q_scope,
        question_id=question_id, is_correct=is_correct, feature=feature, node_id=node_id,
    ))
    if node_id is not None:
        delta_wrong = 0 if is_correct else 1
        delta_fa_correct = 1 if (is_first and is_correct) else 0
        delta_fa_wrong = 1 if (is_first and not is_correct) else 0
        await db.execute(
            pg_insert(StudentKp)
            .values(
                student_id=student_id, node_id=node_id,
                practice_count=1, wrong_count=delta_wrong,
                fa_correct=delta_fa_correct, fa_wrong=delta_fa_wrong,
                last_practice_at=sa.func.now(), source_tags=["practice"], in_scope=True,
            )
            .on_conflict_do_update(
                index_elements=["student_id", "node_id"],
                set_={
                    "practice_count": StudentKp.practice_count + 1,
                    "wrong_count": StudentKp.wrong_count + delta_wrong,
                    "fa_correct": StudentKp.fa_correct + delta_fa_correct,
                    "fa_wrong": StudentKp.fa_wrong + delta_fa_wrong,
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
