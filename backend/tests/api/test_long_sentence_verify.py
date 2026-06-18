"""L3 长难句验证·客观题:取题型/取题(无答案)/ 连对达标判句法node掌握 / 错则收口 wrong_record。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp, WrongRecord
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services import long_sentence_service as lss

_TAG = "lsverify"


async def _seed():
    node_id, ls_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(LongSentence(id=ls_id, scope="platform", source_kind="platform_real",
                            text="The book which covers grammar is very useful for the exam.",
                            analysis_json={"main_clause": "The book is useful",
                                           "translation": "[译]…", "syntax_points": ["定语从句"]},
                            status="published"))
        await db.flush()
        db.add(LongSentenceNode(long_sentence_id=ls_id, node_id=node_id))
        await db.commit()
    return node_id, ls_id


async def _cleanup(node_id, *students):
    async with _async_session_factory() as db:
        for s in students:
            await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(s)})
            await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(s)})
            await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(s)})
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE text LIKE :p"), {"p": "The book which covers grammar%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_verify_objective_types_available():
    node_id, ls_id = await _seed()
    try:
        async with _async_session_factory() as db:
            types = await lss.enabled_verify_types(db)
            assert {"cloze", "struct_type", "main_clause"} <= set(types)
            # 取结构题:有 prompt/options,选项含答案"定语从句"
            q = lss.build_verify(
                (await db.execute(select(LongSentence).where(LongSentence.id == ls_id))).scalar_one(),
                "struct_type")
            assert q["answer"] == "定语从句" and "定语从句" in q["options"]
    finally:
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_verify_mastery_after_required_pass():
    node_id, ls_id = await _seed()
    stu_a, stu_b = uuid.uuid4(), uuid.uuid4()
    try:
        # A:连对 3 次(required_pass=3)→ 第3次判句法node掌握
        async with _async_session_factory() as db:
            r1 = await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="struct_type", answer="定语从句")
            r2 = await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="struct_type", answer="定语从句")
            r3 = await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="struct_type", answer="定语从句")
            await db.commit()
            assert r1["correct"] and not r1["mastered_nodes"]
            assert r3["mastered_nodes"] == ["定语从句"]
        async with _async_session_factory() as db:
            sk = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == stu_a, StudentKp.node_id == node_id))).scalar_one()
            assert float(sk.mastery) == 1.0 and sk.practice_count == 3

        # B:答错 → 进 wrong_record,不判掌握
        async with _async_session_factory() as db:
            rb = await lss.submit_verify(db, student_id=stu_b, ls_id=ls_id, verify_type="struct_type", answer="状语从句")
            await db.commit()
            assert rb["correct"] is False and rb["correct_answer"] == "定语从句"
        async with _async_session_factory() as db:
            wc = (await db.execute(select(func.count()).select_from(WrongRecord)
                  .where(WrongRecord.student_id == stu_b, WrongRecord.node_id == node_id))).scalar_one()
            assert wc == 1
    finally:
        await _cleanup(node_id, stu_a, stu_b)
