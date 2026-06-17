"""R3.3 判掌握:作答落 answer_log+student_kp;原题+N仿真全对→错题掌握+student_kp.mastery=1。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    PlatformQuestion, PlatformQuestionKp, StudentKp, WrongRecord,
)
from app.services import mastery_judge_service as mj

_TAG = "mjudge"


async def _seed():
    """node + 原题(platform real) + 3 道 sim(挂 node) + 1 条 open 错题(原题)。"""
    node_id, orig_id = uuid.uuid4(), uuid.uuid4()
    sim_ids = [uuid.uuid4() for _ in range(3)]
    student = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(PlatformQuestion(id=orig_id, type="real", stem=f"{_TAG} 原题", answer="A",
                                question_type="单选", status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=orig_id, node_id=node_id))
        for sid in sim_ids:
            db.add(PlatformQuestion(id=sid, type="sim", parent_real_id=orig_id, is_fallback=False,
                                    stem=f"{_TAG} 仿真", answer="A", question_type="单选", status="published"))
            await db.flush()
            db.add(PlatformQuestionKp(question_id=sid, node_id=node_id))
        db.add(WrongRecord(id=uuid.uuid4(), student_id=student, q_scope="platform",
                           question_id=orig_id, node_id=node_id, status="open"))
        await db.commit()
    return {"node": node_id, "orig": orig_id, "sims": sim_ids, "student": student}


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_judge_mastery_full_pass():
    s = await _seed()
    try:
        async with _async_session_factory() as db:
            # 原题 + 3 仿真全做对
            await mj.log_answer(db, student_id=s["student"], q_scope="platform",
                                question_id=s["orig"], node_id=s["node"], is_correct=True)
            for sid in s["sims"]:
                await mj.log_answer(db, student_id=s["student"], q_scope="platform",
                                    question_id=sid, node_id=s["node"], is_correct=True)
            await db.commit()
            mastered = await mj.judge_and_mark(
                db, student_id=s["student"], node_id=s["node"],
                original_question_id=s["orig"], original_q_scope="platform", required_sims=3)
            await db.commit()
            assert mastered is True

        async with _async_session_factory() as db:
            wr = (await db.execute(select(WrongRecord).where(
                WrongRecord.student_id == s["student"], WrongRecord.question_id == s["orig"]))).scalar_one()
            assert wr.status == "mastered" and wr.mastery_source == "auto" and wr.mastered_at is not None
            kp = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == s["student"], StudentKp.node_id == s["node"]))).scalar_one()
            assert float(kp.mastery) == 1.0
            assert kp.practice_count == 4   # 原题 + 3 仿真
    finally:
        await _cleanup(s["student"], s["node"])


@pytest.mark.asyncio
async def test_judge_not_enough_sims():
    s = await _seed()
    try:
        async with _async_session_factory() as db:
            await mj.log_answer(db, student_id=s["student"], q_scope="platform",
                                question_id=s["orig"], node_id=s["node"], is_correct=True)
            # 只做对 2 道仿真(< N=3)
            for sid in s["sims"][:2]:
                await mj.log_answer(db, student_id=s["student"], q_scope="platform",
                                    question_id=sid, node_id=s["node"], is_correct=True)
            await db.commit()
            mastered = await mj.judge_and_mark(
                db, student_id=s["student"], node_id=s["node"],
                original_question_id=s["orig"], original_q_scope="platform", required_sims=3)
            await db.commit()
            assert mastered is False
        async with _async_session_factory() as db:
            wr = (await db.execute(select(WrongRecord).where(
                WrongRecord.student_id == s["student"], WrongRecord.question_id == s["orig"]))).scalar_one()
            assert wr.status == "open"   # 未判掌握
    finally:
        await _cleanup(s["student"], s["node"])
