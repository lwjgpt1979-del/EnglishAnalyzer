"""R1.1 unit_node 边表 schema smoke + stages_from_grades 共享工具。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import stages_from_grades

_TAG = "unitnode"


def test_stages_from_grades():
    assert stages_from_grades(["小学5年级"]) == ["小"]
    assert stages_from_grades(["初中7年级", "高中1年级"]) == ["初", "高"]
    assert stages_from_grades(["小学5年级", "小学6年级"]) == ["小"]   # 去重
    assert stages_from_grades([]) == []
    assert stages_from_grades(None) == []


@pytest.mark.asyncio
async def test_unit_node_edge():
    unit_id, n1, n2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            db.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="初中7年级",
                                  semester="上", unit_no=1, unit_title=f"{_TAG}U1"))
            for nid, nm in [(n1, f"{_TAG}定从"), (n2, f"{_TAG}时态")]:
                db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法",
                                     name=nm, code=f"{_TAG}-{nm}", status="active", source="textbook"))
            await db.flush()
            db.add(UnitNode(unit_id=unit_id, node_id=n1, source="ai_extract"))
            db.add(UnitNode(unit_id=unit_id, node_id=n2, source="ai_extract"))
            await db.commit()

        async with _async_session_factory() as db:
            nodes = (await db.execute(
                select(UnitNode.node_id).where(UnitNode.unit_id == unit_id)
            )).scalars().all()
            assert set(nodes) == {n1, n2}   # 一单元多 KP
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
            await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
            await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
            await db.commit()
