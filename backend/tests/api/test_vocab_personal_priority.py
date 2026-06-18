"""R5.4 背词来源收敛:个人体系命中词(student_kp→vocab_node)优先于教材词。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import VocabularyWord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d18_vocab_kg import VocabNode
from app.services import vocabulary_service as vs

_TAG = "vpp"
VER, GRADE, SEM = f"{_TAG}版", "初中7年级", "上"


async def _mk_word(db, suffix, diff=3) -> uuid.UUID:
    wid = uuid.uuid4()
    db.add(VocabularyWord(id=wid, word=f"{_TAG}{suffix}", definitions=[{"pos": "n", "meaning": "x"}],
                          difficulty=diff, type="word"))
    return wid


@pytest.mark.asyncio
async def test_personal_kp_word_ranks_first():
    student = uuid.uuid4()
    unit_id, node_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(User(id=student, openid=f"{_TAG}_{student.hex[:8]}", role="student",
                    preferred_textbook_version=VER, preferred_grade=GRADE, preferred_semester=SEM))
        db.add(CurriculumUnit(id=unit_id, textbook_version=VER, grade=GRADE,
                              semester=SEM, unit_no=1, unit_title=f"{_TAG}U"))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="词汇", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        w_p0 = await _mk_word(db, "personal", diff=1)   # 个人命中词(难度低,若同级会更靠前,但 P0 应压过教材)
        w_p1 = await _mk_word(db, "textbook", diff=1)   # 教材词
        await db.flush()
        # P0:student_kp in_scope + vocab_node(w_p0 → node)
        db.add(StudentKp(student_id=student, node_id=node_id, in_scope=True, source_tags=["wrong_hit"]))
        db.add(VocabNode(word_id=w_p0, node_id=node_id, source="exam"))
        # P1:教材词
        db.add(CurriculumWord(unit_id=unit_id, word_id=w_p1, is_core=True, sort_order=0))
        await db.commit()
    try:
        async with _async_session_factory() as db:
            user = (await db.execute(select(User).where(User.id == student))).scalar_one()
            words = await vs._ordered_new_words(db, student=user, limit=10)
            ids = [w.id for w in words]
            assert w_p0 in ids and w_p1 in ids
            # 个人体系命中词排在教材词之前(P0 < P1)
            assert ids.index(w_p0) < ids.index(w_p1)
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM vocab_node WHERE node_id = :n"), {"n": str(node_id)})
            await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
            await db.execute(text("DELETE FROM curriculum_words WHERE unit_id = :u"), {"u": str(unit_id)})
            await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
            await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
            await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": VER})
            await db.execute(text("DELETE FROM users WHERE id = :s"), {"s": str(student)})
            await db.commit()
