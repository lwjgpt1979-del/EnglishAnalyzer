"""R4.2 知识地图:默认只亮已练已错 / include_all 展开全集 / status 分类 / summary。"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.services import student_graph_service as sg

_TAG = "sgview"


async def _seed(student):
    """4 节点:未学(in_scope) / 已练 / 薄弱(有错) / 已掌握。"""
    nodes = {k: uuid.uuid4() for k in ("unlearned", "practiced", "weak", "mastered")}
    async with _async_session_factory() as db:
        for k, nid in nodes.items():
            db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}{k}",
                                 code=f"{_TAG}-{k}", status="active", source="seed"))
        await db.flush()
        db.add(StudentKp(student_id=student, node_id=nodes["unlearned"], practice_count=0,
                         wrong_count=0, in_scope=True, source_tags=["textbook"]))
        db.add(StudentKp(student_id=student, node_id=nodes["practiced"], practice_count=4,
                         wrong_count=0, in_scope=True, source_tags=["textbook", "practice"]))
        db.add(StudentKp(student_id=student, node_id=nodes["weak"], practice_count=3,
                         wrong_count=2, in_scope=True, source_tags=["wrong_hit"]))
        db.add(StudentKp(student_id=student, node_id=nodes["mastered"], practice_count=5,
                         wrong_count=1, mastery=Decimal("1.0"), in_scope=True, source_tags=["practice"]))
        await db.commit()
    return nodes


async def _cleanup(student):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_graph_default_and_expand():
    student = uuid.uuid4()
    nodes = await _seed(student)
    try:
        async with _async_session_factory() as db:
            # 默认:只亮已练/已错(practiced/weak/mastered),不含 unlearned
            g = await sg.get_graph(db, student_id=student)
            ids = {r["node_id"] for r in g}
            assert nodes["unlearned"] not in ids
            assert {nodes["practiced"], nodes["weak"], nodes["mastered"]} <= ids
            status = {r["node_id"]: r["status"] for r in g}
            assert status[nodes["weak"]] == "weak"
            assert status[nodes["practiced"]] == "practiced"
            assert status[nodes["mastered"]] == "mastered"

            # 展开全集:含 unlearned
            gall = await sg.get_graph(db, student_id=student, include_all=True)
            allids = {r["node_id"] for r in gall}
            assert nodes["unlearned"] in allids
            un = next(r for r in gall if r["node_id"] == nodes["unlearned"])
            assert un["status"] == "unlearned"

            # summary
            s = await sg.graph_summary(db, student_id=student)
            assert s == {"in_scope": 4, "practiced": 3, "weak": 1, "mastered": 1}
    finally:
        await _cleanup(student)
