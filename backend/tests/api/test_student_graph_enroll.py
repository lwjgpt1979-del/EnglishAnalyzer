"""R4.1 个人图谱物化:选教材批量纳入 / 不覆盖练习数据 / 多来源去重追加 / 幂等。"""
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

_TAG = "sgenroll"
VER, GRADE, SEM = f"{_TAG}版", "初中7年级", "上"


async def _seed():
    unit_id = uuid.uuid4()
    n1, n2 = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=VER, grade=GRADE,
                              semester=SEM, unit_no=1, unit_title=f"{_TAG}U1"))
        for i, nid in enumerate((n1, n2)):
            db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法",
                                 name=f"{_TAG}KP{i}", code=f"{_TAG}-{i}", status="active", source="seed"))
        await db.flush()
        db.add(UnitNode(unit_id=unit_id, node_id=n1, source="ai_extract"))
        db.add(UnitNode(unit_id=unit_id, node_id=n2, source="ai_extract"))
        await db.commit()
    return n1, n2


async def _cleanup(student, *nodes):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM unit_node WHERE node_id = ANY(:ns)"),
                         {"ns": [str(n) for n in nodes]})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": VER})
        await db.commit()


@pytest.mark.asyncio
async def test_enroll_textbook_and_preserve_practice():
    n1, n2 = await _seed()
    student = uuid.uuid4()
    try:
        # n1 已有练习数据(模拟先练后选教材)
        async with _async_session_factory() as db:
            db.add(StudentKp(student_id=student, node_id=n1, practice_count=5, wrong_count=2,
                             source_tags=["practice"], in_scope=False))
            await db.commit()

        async with _async_session_factory() as db:
            cnt = await sg.enroll_textbook(db, student_id=student,
                                           textbook_version=VER, grade=GRADE, semester=SEM)
            await db.commit()
            assert cnt == 2

        async with _async_session_factory() as db:
            rows = {r.node_id: r for r in (await db.execute(
                select(StudentKp).where(StudentKp.student_id == student))).scalars().all()}
            assert set(rows) == {n1, n2}
            # n1:练习数据保留,in_scope 置真,来源含 practice+textbook
            assert rows[n1].practice_count == 5 and rows[n1].in_scope is True
            assert set(rows[n1].source_tags) == {"practice", "textbook"}
            # n2:新纳入
            assert rows[n2].in_scope is True and rows[n2].source_tags == ["textbook"]

        # 幂等 + 多来源:再纳入 + add_source('wrong_hit')
        async with _async_session_factory() as db:
            await sg.enroll_textbook(db, student_id=student, textbook_version=VER, grade=GRADE, semester=SEM)
            await sg.add_source(db, student_id=student, node_id=n2, tag="wrong_hit")
            await db.commit()
        async with _async_session_factory() as db:
            r1 = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == n1))).scalar_one()
            r2 = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == n2))).scalar_one()
            assert set(r1.source_tags) == {"practice", "textbook"}    # 去重,不重复 textbook
            assert set(r2.source_tags) == {"textbook", "wrong_hit"}
    finally:
        await _cleanup(student, n1, n2)
