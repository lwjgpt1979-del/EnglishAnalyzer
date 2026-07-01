"""教材长难句抽取改自「单元解析句子」(unit_section_sentence) + 按单元幂等。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d20_long_sentence import LongSentence
from app.models.d22_unit_structured import UnitSection, UnitSectionSentence
from app.services.kp_normalize import normalize_kp_name
from app.services import long_sentence_service as lss

_TAG = "lstb"
LONG = ("The book that the teacher recommended to all the students in our class last "
        "week which covers advanced grammar is extremely useful for the final exam.")
SHORT = "I like apples."


async def _seed():
    unit_id = uuid.uuid4()
    tb = f"教材抽取版{uuid.uuid4().hex[:6]}"
    norm = normalize_kp_name("定语从句")
    async with _async_session_factory() as db:
        # 「定语从句」别称全局唯一:已存在(种子库常有)则复用其节点,否则新建,避免唯一冲突
        node_id = (await db.execute(select(NodeAlias.node_id).where(
            NodeAlias.alias_norm == norm))).scalar_one_or_none()
        _own_node = node_id is None
        if _own_node:
            node_id = uuid.uuid4()
            db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                                 code=f"{_TAG}-dingyu", status="active", source="seed"))
            await db.flush()
            db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias="定语从句",
                             alias_norm=norm, source="seed"))
        db.add(CurriculumUnit(id=unit_id, textbook_version=tb, grade="九年级",
                              semester="上", unit_no=1, unit_title="U1"))
        await db.flush()
        sec_id = uuid.uuid4()
        db.add(UnitSection(id=sec_id, unit_id=unit_id, kind="grammar",
                           point_name="定语从句", sort_order=0))
        await db.flush()
        db.add(UnitSectionSentence(id=uuid.uuid4(), section_id=sec_id, text=LONG,
                                   difficulty=70, sort_order=0))
        db.add(UnitSectionSentence(id=uuid.uuid4(), section_id=sec_id, text=SHORT,
                                   difficulty=5, sort_order=1))
        await db.commit()
    return node_id, unit_id, _own_node


async def _cleanup(node_id, unit_id, own_node):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text(
            "DELETE FROM curriculum_unit_section_sentence WHERE section_id IN "
            "(SELECT id FROM curriculum_unit_section WHERE unit_id = :u)"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM curriculum_unit_section WHERE unit_id = :u"), {"u": str(unit_id)})
        await db.execute(text("DELETE FROM curriculum_units WHERE id = :u"), {"u": str(unit_id)})
        if own_node:   # 仅删本测试新建的节点/别称;复用种子库的不动
            await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm = :a"),
                             {"a": normalize_kp_name("定语从句")})
            await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_extract_from_textbook_sections_and_idempotent():
    node_id, unit_id, own_node = await _seed()
    try:
        async with _async_session_factory() as db:
            st = await lss.extract_from_textbook(db, filters={"unit_ids": [unit_id]})
            assert st.created == 1 and st.long_kept == 1   # 只 LONG 入选,SHORT 词数不足被滤
            assert "定语从句" in st.syntax_points

        async with _async_session_factory() as db:
            ls = (await db.execute(select(LongSentence).where(
                LongSentence.unit_id == unit_id))).scalar_one()
            assert ls.text.startswith("The book") and ls.source_kind == "textbook"
            assert ls.source_passage_id is None          # 不再来自短文

        # 幂等:该单元已抽过 → 跳过,不新增
        async with _async_session_factory() as db:
            st2 = await lss.extract_from_textbook(db, filters={"unit_ids": [unit_id]})
            assert st2.created == 0 and st2.skipped_done == 1
            cnt = (await db.execute(select(func.count()).select_from(LongSentence)
                   .where(LongSentence.unit_id == unit_id))).scalar_one()
            assert cnt == 1
    finally:
        await _cleanup(node_id, unit_id, own_node)
