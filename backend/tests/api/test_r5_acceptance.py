"""R5 验收闭环:教材词挂node → 选教材纳入 → 个人体系命中词进背词来源;通用词库导入。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import VocabularyWord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d17_curriculum_kg import UnitNode
from app.models.d18_vocab_kg import VocabNode, VocabListItem
from app.services import vocab_kg_service as vkg
from app.services import student_graph_service as sg
from app.services import vocab_list_service as vls

_TAG = "r5acc"
VER, GRADE, SEM = f"{_TAG}版", "初中7年级", "上"


async def _cleanup(student, word_id, node_id, unit_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM vocab_list_item WHERE word_id = :w"), {"w": str(word_id)})
        await db.execute(text("DELETE FROM vocab_list WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM vocab_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM curriculum_words WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": VER})
        await db.commit()


@pytest.mark.asyncio
async def test_r5_vocab_loop():
    student = uuid.uuid4()
    unit_id, node_id, word_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=VER, grade=GRADE,
                              semester=SEM, unit_no=1, unit_title=f"{_TAG}U"))
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="词汇", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(VocabularyWord(id=word_id, word=f"{_TAG}abandon", definitions=[{"pos": "v", "meaning": "放弃"}],
                              difficulty=3, type="word"))
        await db.flush()
        db.add(CurriculumWord(unit_id=unit_id, word_id=word_id, is_core=True, sort_order=0))
        db.add(UnitNode(unit_id=unit_id, node_id=node_id))   # 单元↔node(R1)
        await db.commit()
    try:
        # 1) 教材词 × 单元 node 派生 vocab_node
        async with _async_session_factory() as db:
            created = await vkg.derive_unit_vocab_nodes(db, unit_id=unit_id)
            await db.commit()
            assert created == 1
            assert (await db.execute(select(VocabNode.node_id).where(
                VocabNode.word_id == word_id))).scalar_one() == node_id

        # 2) 学生选教材 → 纳入 student_kp(in_scope)
        async with _async_session_factory() as db:
            n = await sg.enroll_textbook(db, student_id=student,
                                         textbook_version=VER, grade=GRADE, semester=SEM)
            await db.commit()
            assert n == 1

        # 3) 个人体系命中词 = 该教材词(背词来源收敛)
        async with _async_session_factory() as db:
            words = await vkg.personal_kp_words(db, student_id=student, limit=10)
            assert {w.id for w in words} == {word_id}

        # 4) 通用词库:建库 + 导入该词(共享同一词条)
        async with _async_session_factory() as db:
            vl = await vls.create_list(db, name=f"{_TAG}高考3500", exam_level="senior",
                                       source_type="official_syllabus", status="published")
            await vls.add_items(db, list_id=vl.id, items=[{"word": f"{_TAG}abandon", "rank": 1, "star": 5}])
            await db.commit()
            item = (await db.execute(select(VocabListItem).where(VocabListItem.list_id == vl.id))).scalar_one()
            assert item.word_id == word_id and item.star == 5   # 复用同一词条
    finally:
        await _cleanup(student, word_id, node_id, unit_id)
