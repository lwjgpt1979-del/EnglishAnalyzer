"""R3.1 错题中心:收口 record_wrong(upsert)/ 复发重开 / list_open_wrongs。"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import WrongRecord
from app.services import wrong_center_service as wc

_TAG = "wctr"


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.commit()
    return nid


async def _cleanup(student_id, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student_id)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_record_wrong_upsert_and_reopen():
    node_id = await _seed_node()
    student = uuid.uuid4()
    q1 = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            wid = await wc.record_wrong(db, student_id=student, q_scope="platform",
                                        question_id=q1, node_id=node_id)
            await db.commit()
        async with _async_session_factory() as db:
            r = (await db.execute(select(WrongRecord).where(WrongRecord.id == wid))).scalar_one()
            assert r.status == "open" and r.node_id == node_id
            assert r.next_review_at == _dt.date.today()
            # 人工置掌握
            r.status = "mastered"
            r.mastered_at = _dt.datetime.now(_dt.timezone.utc)
            r.review_count = 3
            await db.commit()

        # 同题复发 → 重开、SM-2 归零、不新建行
        async with _async_session_factory() as db:
            wid2 = await wc.record_wrong(db, student_id=student, q_scope="platform",
                                         question_id=q1, node_id=node_id)
            await db.commit()
            assert wid2 == wid
        async with _async_session_factory() as db:
            r = (await db.execute(select(WrongRecord).where(WrongRecord.id == wid))).scalar_one()
            assert r.status == "open" and r.mastered_at is None and r.review_count == 0
            cnt = (await db.execute(
                select(func.count()).select_from(WrongRecord).where(WrongRecord.student_id == student)
            )).scalar_one()
            assert cnt == 1   # upsert,不重复
    finally:
        await _cleanup(student, node_id)


@pytest.mark.asyncio
async def test_list_open_wrongs_filter():
    node_id = await _seed_node()
    student = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            await wc.record_wrong(db, student_id=student, q_scope="uploaded",
                                  question_id=uuid.uuid4(), node_id=node_id)
            await wc.record_wrong(db, student_id=student, q_scope="platform",
                                  question_id=uuid.uuid4(), node_id=None)
            await db.commit()
        async with _async_session_factory() as db:
            allw = await wc.list_open_wrongs(db, student_id=student)
            assert len(allw) == 2
            byn = await wc.list_open_wrongs(db, student_id=student, node_id=node_id)
            assert len(byn) == 1 and byn[0].node_id == node_id
    finally:
        await _cleanup(student, node_id)
