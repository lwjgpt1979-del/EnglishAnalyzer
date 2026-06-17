"""R4.4 个人图谱趋势:answer_log 按 node+日聚合 accuracy。"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy import text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp, AnswerLog
from app.services import student_graph_service as sg

_TAG = "sgtrend"


async def _seed():
    node_id, q1, q2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    student = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        for q in (q1, q2):
            db.add(PlatformQuestion(id=q, type="sim", is_fallback=True, stem=f"{_TAG} 题",
                                    question_type="单选", status="published"))
            await db.flush()
            db.add(PlatformQuestionKp(question_id=q, node_id=node_id))
        await db.commit()
    return student, node_id, q1, q2


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_node_trend_daily_accuracy():
    student, node_id, q1, q2 = await _seed()
    today = _dt.date(2026, 6, 17)
    d1 = _dt.datetime(2026, 6, 16, 10, tzinfo=_dt.timezone.utc)
    d2 = _dt.datetime(2026, 6, 17, 10, tzinfo=_dt.timezone.utc)
    try:
        async with _async_session_factory() as db:
            # 6-16:1 对 1 错 → accuracy 0.5;6-17:1 对 → 1.0
            db.add(AnswerLog(id=uuid.uuid4(), student_id=student, q_scope="platform",
                             question_id=q1, is_correct=True, answered_at=d1))
            db.add(AnswerLog(id=uuid.uuid4(), student_id=student, q_scope="platform",
                             question_id=q2, is_correct=False, answered_at=d1))
            db.add(AnswerLog(id=uuid.uuid4(), student_id=student, q_scope="platform",
                             question_id=q1, is_correct=True, answered_at=d2))
            await db.commit()

        async with _async_session_factory() as db:
            pts = await sg.node_trend(db, student_id=student, node_id=node_id, days=30, today=today)
            by_date = {p["date"]: p for p in pts}
            assert by_date[_dt.date(2026, 6, 16)]["accuracy"] == 0.5
            assert by_date[_dt.date(2026, 6, 16)]["correct"] == 1 and by_date[_dt.date(2026, 6, 16)]["wrong"] == 1
            assert by_date[_dt.date(2026, 6, 17)]["accuracy"] == 1.0
    finally:
        await _cleanup(student, node_id)
