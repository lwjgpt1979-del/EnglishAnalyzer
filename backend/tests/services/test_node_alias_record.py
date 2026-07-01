"""挂靠时沉淀别称:record_node_alias 去重/冲突;手动挂靠后同名可自动命中。"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d22_unit_structured import UnitSection
from app.services import curriculum_service as cs


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _mk_node(db, name: str) -> KnowledgeNode:
    n = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", name=name,
                      code=f"t-{uuid.uuid4().hex[:8]}", status="active", source="manual")
    db.add(n)
    await db.flush()
    return n


@pytest.mark.asyncio
async def test_record_alias_dedup_and_conflict(db_session):
    a = await _mk_node(db_session, "节点A")
    b = await _mk_node(db_session, "节点B")
    raw = f"数量词{uuid.uuid4().hex[:6]}"

    assert await cs.record_node_alias(db_session, node_id=a.id, raw_name=raw, source="manual") is True
    # 同写法再记一次 → 已存在,跳过
    assert await cs.record_node_alias(db_session, node_id=a.id, raw_name=raw, source="manual") is False
    # 另一节点想抢同写法 → 冲突,跳过(不改 alias 归属)
    assert await cs.record_node_alias(db_session, node_id=b.id, raw_name=raw, source="auto") is False

    rows = (await db_session.execute(
        sa.select(NodeAlias.node_id).where(NodeAlias.alias == raw))).scalars().all()
    assert rows == [a.id]


@pytest.mark.asyncio
async def test_manual_link_records_alias(db_session):
    # 造 cf 根 + 子节点(manual_link 限 cf/jf 子树)
    root = (await db_session.execute(sa.select(KnowledgeNode).where(KnowledgeNode.code == "cf"))).scalar_one_or_none()
    if root is None:
        root = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", name="词法", code="cf",
                             status="active", source="seed")
        db_session.add(root)
        await db_session.flush()
    child = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", parent_id=root.id, name="动名词的构成",
                          code=f"cf-{uuid.uuid4().hex[:6]}", status="active", source="manual")
    db_session.add(child)
    uid = uuid.uuid4()
    db_session.add(CurriculumUnit(id=uid, textbook_version=f"别称版{uuid.uuid4().hex[:5]}",
                                  grade="七年级", semester="上", unit_no=1, unit_title="U1"))
    await db_session.flush()
    src_name = f"动名词 (Gerunds) {uuid.uuid4().hex[:5]}"
    sec = UnitSection(id=uuid.uuid4(), unit_id=uid, kind="grammar", point_name=src_name, sort_order=0)
    db_session.add(sec)
    await db_session.flush()

    await cs.manual_link_section(db_session, section_id=sec.id, node_id=child.id)

    # 来源名应已作为别称挂到该节点
    aid = (await db_session.execute(sa.select(NodeAlias.node_id).where(NodeAlias.alias == src_name))).scalar_one_or_none()
    assert aid == child.id
