"""R3 验收闭环:做错→错题中心→有源练同类(真题派生)→原题+N仿真全对→判掌握回写。

串起 R3 全链:wrong_center.record_wrong → wrong_practice.practice_same_kind(真题派生仿真)
→ mastery_judge.log_answer(原题+N仿真全对)→ judge_and_mark(错题 mastered + student_kp.mastery=1)。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    PlatformQuestion, PlatformQuestionKp, WrongRecord, StudentKp,
)
from app.services import wrong_center_service as wc
from app.services import wrong_practice_service as wp
from app.services import mastery_judge_service as mj

_TAG = "r3acc"


async def _seed_node_with_real():
    node_id, real_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(PlatformQuestion(id=real_id, type="real", stem=f"{_TAG} 原题真题", answer="A",
                                question_type="单选", status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=real_id, node_id=node_id))
        await db.commit()
    return node_id, real_id


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"%{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_r3_wrong_loop():
    node_id, real_id = await _seed_node_with_real()
    student = uuid.uuid4()
    try:
        # 1) 做错原题(真题)→ 进错题中心
        async with _async_session_factory() as db:
            await wc.record_wrong(db, student_id=student, q_scope="platform",
                                  question_id=real_id, node_id=node_id)
            await db.commit()

        # 2) 有源练同类:该 node 有真题 → 派生 3 道仿真
        async with _async_session_factory() as db:
            res = await wp.practice_same_kind(db, node_id=node_id, count=3)
            await db.commit()
            assert res.real_id == real_id and not res.fallback and len(res.sim_ids) == 3
            sim_ids = res.sim_ids

        # 3) 原题 + 3 仿真全做对(作答落 answer_log + student_kp)
        async with _async_session_factory() as db:
            await mj.log_answer(db, student_id=student, q_scope="platform",
                                question_id=real_id, node_id=node_id, is_correct=True)
            for sid in sim_ids:
                await mj.log_answer(db, student_id=student, q_scope="platform",
                                    question_id=sid, node_id=node_id, is_correct=True)
            await db.commit()

        # 4) 判掌握 → 错题 mastered + student_kp.mastery=1
        async with _async_session_factory() as db:
            mastered = await mj.judge_and_mark(
                db, student_id=student, node_id=node_id,
                original_question_id=real_id, original_q_scope="platform", required_sims=3)
            await db.commit()
            assert mastered is True

        async with _async_session_factory() as db:
            wr = (await db.execute(select(WrongRecord).where(
                WrongRecord.student_id == student, WrongRecord.question_id == real_id))).scalar_one()
            assert wr.status == "mastered" and wr.mastery_source == "auto"
            kp = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == node_id))).scalar_one()
            assert float(kp.mastery) == 1.0
            # 所有练习仿真必有源(派生自真题)
            sims = (await db.execute(select(PlatformQuestion).where(
                PlatformQuestion.id.in_(sim_ids)))).scalars().all()
            assert all(s.parent_real_id == real_id for s in sims)
    finally:
        await _cleanup(student, node_id)
