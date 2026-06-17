"""R2.4 历史题迁移:exam→real(挂node)/ 有源sim→parent / 无源sim→fallback / 幂等。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import ExamPaper, ExamQuestion, ExamQuestionKnowledgePoint, SimulatedQuestion
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from migrate_questions_to_platform import migrate  # noqa: E402

_TAG = "mq2pq"
KPNAME = f"{_TAG}一般现在时"


async def _seed():
    ids = {}
    async with _async_session_factory() as db:
        node_id = uuid.uuid4()
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=KPNAME,
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias=KPNAME,
                         alias_norm=normalize_kp_name(KPNAME), source="seed"))
        kp = KnowledgePoint(id=uuid.uuid4(), code=f"{_TAG}-kp", name=KPNAME, category="grammar",
                            applicable_grades=["初中7年级"], applicable_textbooks=[f"{_TAG}版"])
        db.add(kp)
        paper = ExamPaper(id=uuid.uuid4(), source="official_seed", textbook_version=f"{_TAG}版",
                          grade="初中7年级", semester="上", title=f"{_TAG}卷", status="published")
        db.add(paper)
        await db.flush()
        eq = ExamQuestion(id=uuid.uuid4(), paper_id=paper.id, question_no="1", question_type="单选",
                          stem=f"{_TAG} 真题题干", answer="A", difficulty=3)
        db.add(eq)
        await db.flush()
        db.add(ExamQuestionKnowledgePoint(exam_question_id=eq.id, knowledge_point_id=kp.id))
        sim_p = SimulatedQuestion(id=uuid.uuid4(), source_exam_question_id=eq.id,
                                  knowledge_point_id=kp.id, question_type="单选",
                                  stem=f"{_TAG} 有源仿真", answer="A", difficulty=3, status="published")
        sim_o = SimulatedQuestion(id=uuid.uuid4(), source_exam_question_id=None,
                                  knowledge_point_id=kp.id, question_type="单选",
                                  stem=f"{_TAG} 无源仿真", answer="B", difficulty=3, status="published")
        db.add_all([sim_p, sim_o])
        await db.commit()
        ids = {"node": node_id, "paper": paper.id, "eq": eq.id, "sim_p": sim_p.id, "sim_o": sim_o.id}
    return ids


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE question_id IN "
                              "(SELECT id FROM platform_question WHERE stem LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM simulated_questions WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM exam_question_knowledge_points WHERE exam_question_id IN "
                              "(SELECT id FROM exam_questions WHERE stem LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM exam_questions WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM exam_papers WHERE title LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_points WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_migrate_questions_idempotent():
    ids = await _seed()
    try:
        st = await migrate(dry=False, only_exam_ids={ids["eq"]}, only_sim_ids={ids["sim_p"], ids["sim_o"]})
        assert st.real == 1
        assert st.sim_parent == 1 and st.sim_fallback == 1
        assert st.kp_edges >= 2   # 真题 + 至少有源仿真挂 node

        async with _async_session_factory() as db:
            real = (await db.execute(
                select(PlatformQuestion).where(
                    PlatformQuestion.meta["legacy_exam_question_id"].astext == str(ids["eq"]))
            )).scalar_one()
            assert real.type == "real"
            # 真题挂 node
            edge = (await db.execute(
                select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == real.id)
            )).scalar_one()
            assert edge == ids["node"]
            # 有源仿真 → parent=real
            sim_p = (await db.execute(
                select(PlatformQuestion).where(
                    PlatformQuestion.meta["legacy_sim_id"].astext == str(ids["sim_p"]))
            )).scalar_one()
            assert sim_p.type == "sim" and sim_p.parent_real_id == real.id and sim_p.is_fallback is False
            # 无源仿真 → fallback
            sim_o = (await db.execute(
                select(PlatformQuestion).where(
                    PlatformQuestion.meta["legacy_sim_id"].astext == str(ids["sim_o"]))
            )).scalar_one()
            assert sim_o.is_fallback is True and sim_o.parent_real_id is None

        # 幂等:复跑全部跳过
        st2 = await migrate(dry=False, only_exam_ids={ids["eq"]}, only_sim_ids={ids["sim_p"], ids["sim_o"]})
        assert st2.real == 0 and st2.real_skip == 1
        assert st2.sim_skip == 2 and st2.sim_parent == 0 and st2.sim_fallback == 0
    finally:
        await _cleanup()
