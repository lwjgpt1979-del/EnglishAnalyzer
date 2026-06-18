"""R7 验收闭环(收官):多渠道错题(单题/听力/作业)经统一原子汇入 wrong_record 中心,
口语复习从中心读取。验证应用层错题口径统一到 KP-First 骨架。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import WrongRecord
from app.services.kp_normalize import normalize_kp_name
from app.services import ingest_service as ing
from app.services import wrong_center_service as wc
from app.services import speaking_dialogue_service as sds

_TAG = "r7acc"
HIT = f"{_TAG}定语从句"


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=HIT,
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=HIT,
                         alias_norm=normalize_kp_name(HIT), source="seed"))
        await db.commit()
    return nid


async def _cleanup(student, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM uploaded_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_r7_all_channels_into_one_center():
    node_id = await _seed_node()
    student = uuid.uuid4()
    try:
        # 渠道① 单题/整卷(上传拆题)→ ingest_parsed:uploaded_question + wrong_record(挂 node)
        async with _async_session_factory() as db:
            res = await ing.ingest_parsed(
                db, owner_scope="student", owner_id=student,
                items=[ing.IngestItem(stem="The book ___ I read.", student_answer="who",
                                      correct_answer="which", is_wrong=True, kp_name=HIT)])
            await db.commit()
            assert res[0].node_id == node_id and res[0].wrong_record_id is not None

        # 渠道② 听力答错(无 KP)→ record_wrong_answer:wrong_record(node 空)
        # 渠道③ 作业答错(有 KP)→ record_wrong_answer:wrong_record(挂 node)
        async with _async_session_factory() as db:
            await ing.record_wrong_answer(db, student_id=student, q_scope="platform",
                                          question_id=uuid.uuid4(), kp_name=None)
            await ing.record_wrong_answer(db, student_id=student, q_scope="uploaded",
                                          question_id=uuid.uuid4(), kp_name=HIT)
            await db.commit()

        # 全渠道汇入同一个中心 wrong_record
        async with _async_session_factory() as db:
            total = (await db.execute(select(func.count()).select_from(WrongRecord)
                     .where(WrongRecord.student_id == student))).scalar_one()
            assert total == 3
            with_node = (await db.execute(select(func.count()).select_from(WrongRecord)
                         .where(WrongRecord.student_id == student,
                                WrongRecord.node_id == node_id))).scalar_one()
            assert with_node == 2   # 单题 + 作业(有 KP);听力无 KP → node 空
            opens = await wc.list_open_wrongs(db, student_id=student)
            assert len(opens) == 3

        # 口语错题复习从中心读取(uploaded 题有内容)
        async with _async_session_factory() as db:
            top = await sds._top_due_wrong(db, student)
            assert top is not None and "book" in top["stem"] and top["answer"] == "which"
    finally:
        await _cleanup(student, node_id)
