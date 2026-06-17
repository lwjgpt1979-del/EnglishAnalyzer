"""R4 验收闭环:选教材纳入全集 → 练习/错题命中 → 知识地图默认亮弱点·展开全集·多来源。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d17_curriculum_kg import UnitNode
from app.services import student_graph_service as sg
from app.services import wrong_center_service as wc
from app.services import mastery_judge_service as mj

_TAG = "r4acc"
VER, GRADE, SEM = f"{_TAG}版", "初中7年级", "上"


async def _seed():
    unit_id = uuid.uuid4()
    nodes = {k: uuid.uuid4() for k in ("a", "b", "c")}   # 教材全集 3 个
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=VER, grade=GRADE,
                              semester=SEM, unit_no=1, unit_title=f"{_TAG}U1"))
        for k, nid in nodes.items():
            db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}{k}",
                                 code=f"{_TAG}-{k}", status="active", source="seed"))
        await db.flush()
        for nid in nodes.values():
            db.add(UnitNode(unit_id=unit_id, node_id=nid, source="ai_extract"))
        await db.commit()
    return nodes


async def _cleanup(student, nodes):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM unit_node WHERE node_id = ANY(:ns)"),
                         {"ns": [str(n) for n in nodes.values()]})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": VER})
        await db.commit()


@pytest.mark.asyncio
async def test_r4_personal_graph_loop():
    nodes = await _seed()
    student = uuid.uuid4()
    try:
        # 1) 选教材 → 纳入全集 3 个(in_scope, source=textbook, 皆未学)
        async with _async_session_factory() as db:
            cnt = await sg.enroll_textbook(db, student_id=student,
                                           textbook_version=VER, grade=GRADE, semester=SEM)
            await db.commit()
            assert cnt == 3

        # 2) a 练对 / b 做错(作答落计数 + 进错题中心来源追加 wrong_hit)
        async with _async_session_factory() as db:
            await mj.log_answer(db, student_id=student, q_scope="platform",
                                question_id=uuid.uuid4(), node_id=nodes["a"], is_correct=True)
            bq = uuid.uuid4()
            await mj.log_answer(db, student_id=student, q_scope="platform",
                                question_id=bq, node_id=nodes["b"], is_correct=False)
            await wc.record_wrong(db, student_id=student, q_scope="platform",
                                  question_id=bq, node_id=nodes["b"])
            await db.commit()

        async with _async_session_factory() as db:
            # 3) 默认地图:只亮 a(已练)+ b(已错),c(未学)折叠隐藏
            g = await sg.get_graph(db, student_id=student)
            ids = {r["node_id"] for r in g}
            assert nodes["a"] in ids and nodes["b"] in ids and nodes["c"] not in ids
            st = {r["node_id"]: r["status"] for r in g}
            assert st[nodes["a"]] == "practiced" and st[nodes["b"]] == "weak"

            # 4) 展开全集:含 c(未学)
            gall = await sg.get_graph(db, student_id=student, include_all=True)
            assert nodes["c"] in {r["node_id"] for r in gall}

            # 5) b 多来源:textbook(纳入) + wrong_hit(错题命中)
            b = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == nodes["b"]))).scalar_one()
            assert set(b.source_tags) == {"textbook", "wrong_hit"}

            # 6) summary
            s = await sg.graph_summary(db, student_id=student)
            assert s == {"in_scope": 3, "practiced": 2, "weak": 1, "mastered": 0}
    finally:
        await _cleanup(student, nodes)
