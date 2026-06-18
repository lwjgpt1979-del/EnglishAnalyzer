"""L4 长难句验证·主观题:翻译(AI/相似度)、朗读(发音分阈值)判分 + 达标判掌握 / 错则收口。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp, WrongRecord
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services import long_sentence_service as lss

_TAG = "lssubj"
TRANS = "这本书涵盖高级语法对考试非常有用"


async def _seed():
    node_id, ls_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(LongSentence(id=ls_id, scope="platform", source_kind="platform_real",
                            text="The book which covers advanced grammar is very useful for the exam.",
                            analysis_json={"main_clause": "The book is useful", "translation": TRANS,
                                           "layers": [{"type": "定语从句", "text": "which covers advanced grammar"}],
                                           "syntax_points": ["定语从句"]},
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
        await db.execute(text("DELETE FROM long_sentence WHERE text LIKE :p"), {"p": "The book which covers advanced%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_subjective_types_enabled_and_build():
    node_id, ls_id = await _seed()
    try:
        async with _async_session_factory() as db:
            types = await lss.enabled_verify_types(db)
            assert {"translate", "rewrite", "span_label", "read_aloud"} <= set(types)
            ls = (await db.execute(select(LongSentence).where(LongSentence.id == ls_id))).scalar_one()
            tq = lss.build_verify(ls, "translate")
            assert tq["options"] == [] and tq["answer"] == TRANS
            ra = lss.build_verify(ls, "read_aloud")
            assert ra["prompt"].startswith("朗读")
    finally:
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_translate_grade_and_mastery():
    node_id, ls_id = await _seed()
    stu_a, stu_b = uuid.uuid4(), uuid.uuid4()
    try:
        # A:翻译接近参考(dev 相似度判过)× 3 → 判句法 node 掌握
        good = "这本书涵盖高级语法对考试很有用"
        async with _async_session_factory() as db:
            r1 = await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="translate", answer=good)
            await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="translate", answer=good)
            r3 = await lss.submit_verify(db, student_id=stu_a, ls_id=ls_id, verify_type="translate", answer=good)
            await db.commit()
            assert r1["correct"] and r3["mastered_nodes"] == ["定语从句"]
        async with _async_session_factory() as db:
            sk = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == stu_a, StudentKp.node_id == node_id))).scalar_one()
            assert float(sk.mastery) == 1.0

        # B:翻译离谱 → 不过 → 进 wrong_record
        async with _async_session_factory() as db:
            rb = await lss.submit_verify(db, student_id=stu_b, ls_id=ls_id, verify_type="translate", answer="完全无关的胡乱内容")
            await db.commit()
            assert rb["correct"] is False
        async with _async_session_factory() as db:
            wc = (await db.execute(select(func.count()).select_from(WrongRecord)
                  .where(WrongRecord.student_id == stu_b))).scalar_one()
            assert wc == 1
    finally:
        await _cleanup(node_id, stu_a, stu_b)


@pytest.mark.asyncio
async def test_read_aloud_score_threshold():
    node_id, ls_id = await _seed()
    stu = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            hi = await lss.submit_verify(db, student_id=stu, ls_id=ls_id, verify_type="read_aloud", answer="85")
            lo = await lss.submit_verify(db, student_id=stu, ls_id=ls_id, verify_type="read_aloud", answer="30")
            await db.commit()
            assert hi["correct"] is True and lo["correct"] is False
    finally:
        await _cleanup(node_id, stu)
