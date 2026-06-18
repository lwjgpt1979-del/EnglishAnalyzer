"""R5.2 词汇接入服务:教材词×单元node 派生 vocab_node / 个人体系命中词(排除已掌握)。"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import VocabularyWord, VocabularyLearning
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d17_curriculum_kg import UnitNode
from app.models.d18_vocab_kg import VocabNode
from app.services import vocab_kg_service as vkg

_TAG = "vkgsvc"


async def _mk_word(db, suffix) -> uuid.UUID:
    wid = uuid.uuid4()
    db.add(VocabularyWord(id=wid, word=f"{_TAG}{suffix}", definitions=[{"pos": "n", "meaning": "x"}],
                          difficulty=3, type="word"))
    return wid


async def _cleanup(*, words, nodes, unit_id, student=None):
    async with _async_session_factory() as db:
        if student:
            await db.execute(text("DELETE FROM vocabulary_learning WHERE student_id = :s"), {"s": str(student)})
            await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
            await db.execute(text("DELETE FROM users WHERE id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM vocab_node WHERE word_id = ANY(:w)"), {"w": [str(x) for x in words]})
        await db.execute(text("DELETE FROM curriculum_words WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
        await db.commit()


@pytest.mark.asyncio
async def test_derive_unit_vocab_nodes():
    unit_id, n1, n2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="初中7年级",
                              semester="上", unit_no=1, unit_title=f"{_TAG}U"))
        w1, w2 = await _mk_word(db, "a"), await _mk_word(db, "b")
        for nid in (n1, n2):
            db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="词汇", name=f"{_TAG}{nid.hex[:4]}",
                                 code=f"{_TAG}-{nid.hex[:6]}", status="active", source="seed"))
        await db.flush()
        db.add_all([CurriculumWord(unit_id=unit_id, word_id=w1, is_core=True, sort_order=0),
                    CurriculumWord(unit_id=unit_id, word_id=w2, is_core=True, sort_order=1)])
        db.add_all([UnitNode(unit_id=unit_id, node_id=n1), UnitNode(unit_id=unit_id, node_id=n2)])
        await db.commit()
    try:
        async with _async_session_factory() as db:
            created = await vkg.derive_unit_vocab_nodes(db, unit_id=unit_id)
            await db.commit()
            assert created == 4   # 2 词 × 2 node
        async with _async_session_factory() as db:
            cnt = (await db.execute(select(func.count()).select_from(VocabNode)
                   .where(VocabNode.word_id.in_([w1, w2])))).scalar_one()
            assert cnt == 4
            # 幂等复跑不新增
            again = await vkg.derive_unit_vocab_nodes(db, unit_id=unit_id)
            assert again == 0
    finally:
        await _cleanup(words=[w1, w2], nodes=[n1, n2], unit_id=unit_id)


@pytest.mark.asyncio
async def test_personal_kp_words_excludes_mastered():
    unit_id, node_id = uuid.uuid4(), uuid.uuid4()
    student = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(User(id=student, openid=f"{_TAG}_{student.hex[:8]}", role="student"))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="词汇", name=f"{_TAG}KP",
                             code=f"{_TAG}-pn", status="active", source="seed"))
        w1, w2 = await _mk_word(db, "hit1"), await _mk_word(db, "hit2")
        await db.flush()
        db.add_all([VocabNode(word_id=w1, node_id=node_id), VocabNode(word_id=w2, node_id=node_id)])
        db.add(StudentKp(student_id=student, node_id=node_id, in_scope=True, source_tags=["textbook"]))
        await db.commit()
    try:
        async with _async_session_factory() as db:
            words = await vkg.personal_kp_words(db, student_id=student, limit=10)
            assert {w.id for w in words} == {w1, w2}
            # w2 标已掌握 → 排除
            db.add(VocabularyLearning(id=uuid.uuid4(), student_id=student, word_id=w2,
                                      next_review_at=_dt.datetime.now(_dt.timezone.utc), level="mastered"))
            await db.commit()
        async with _async_session_factory() as db:
            words = await vkg.personal_kp_words(db, student_id=student, limit=10)
            assert {w.id for w in words} == {w1}
    finally:
        await _cleanup(words=[w1, w2], nodes=[node_id], unit_id=unit_id, student=student)
