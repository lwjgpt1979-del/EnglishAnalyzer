"""R0.5 题分域 schema smoke:8 表 CRUD + 硬墙隔离 + 月分区 + scoped 过滤。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import select, text

from app.core.database import _async_session_factory, _async_engine
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    PlatformQuestion, UploadedQuestion, Passage,
    PlatformQuestionKp, UploadedQuestionKp, StudentKp, AnswerLog, WrongRecord,
)
from app.services.question_domain import (
    scoped, create_answer_log_partition, answer_log_partition_name,
)

_TAG = "qdom"


@pytest.mark.asyncio
async def test_question_domain_crud_and_isolation():
    node_id = uuid.uuid4()
    passage_id = uuid.uuid4()
    real_id, sim_id = uuid.uuid4(), uuid.uuid4()
    up_id = uuid.uuid4()
    stu = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法",
                                 name=f"{_TAG}定从", code=f"{_TAG}-node", status="active", source="seed"))
            # passage(平台域)
            db.add(Passage(id=passage_id, scope="platform", kind="reading_text",
                           text=f"{_TAG} passage"))
            await db.flush()
            # 平台题:真题 + 由它派生的仿真(self-FK)+ block→passage
            db.add(PlatformQuestion(id=real_id, type="real", block_id=passage_id,
                                    question_no="D1", question_type="阅读",
                                    stem=f"{_TAG} real", status="published"))
            await db.flush()
            db.add(PlatformQuestion(id=sim_id, type="sim", parent_real_id=real_id,
                                    stem=f"{_TAG} sim", status="draft"))
            # 上传题(个人域)
            db.add(UploadedQuestion(id=up_id, owner_scope="student", owner_id=stu,
                                    question_no="3", stem=f"{_TAG} uploaded", is_wrong=True))
            await db.flush()
            # 题↔KP 两域
            db.add(PlatformQuestionKp(question_id=real_id, node_id=node_id))
            db.add(UploadedQuestionKp(question_id=up_id, node_id=node_id))
            # 个人窄表
            db.add(StudentKp(student_id=stu, node_id=node_id, practice_count=1,
                             source_tags=["paper_upload"], in_scope=True))
            db.add(WrongRecord(id=uuid.uuid4(), student_id=stu, q_scope="uploaded",
                               question_id=up_id, node_id=node_id, is_original=True, status="open"))
            db.add(AnswerLog(id=uuid.uuid4(), student_id=stu, q_scope="platform",
                             question_id=real_id, is_correct=True,
                             answered_at=datetime(2026, 6, 15, tzinfo=timezone.utc)))
            await db.commit()

        async with _async_session_factory() as db:
            # 派生链可读
            sim = (await db.execute(select(PlatformQuestion).where(PlatformQuestion.id == sim_id))).scalar_one()
            assert sim.parent_real_id == real_id and sim.type == "sim"
            # 两域题各自挂到同一新 knowledge_nodes
            assert (await db.execute(select(PlatformQuestionKp.node_id)
                    .where(PlatformQuestionKp.question_id == real_id))).scalar_one() == node_id
            assert (await db.execute(select(UploadedQuestionKp.node_id)
                    .where(UploadedQuestionKp.question_id == up_id))).scalar_one() == node_id
            # answer_log 落默认分区,可查
            assert (await db.execute(select(sa.func.count()).select_from(AnswerLog)
                    .where(AnswerLog.student_id == stu))).scalar_one() == 1

        # 硬墙:uploaded_question 无任何指向 platform_question 的外键
        async with _async_engine.begin() as conn:
            fks = await conn.run_sync(lambda c: sa.inspect(c).get_foreign_keys("uploaded_question"))
        referred = {fk["referred_table"] for fk in fks}
        assert "platform_question" not in referred
        assert referred <= {"passage"}   # 仅允许引用 passage(题块语料)
    finally:
        await _cleanup(node_id, stu)


@pytest.mark.asyncio
async def test_answer_log_monthly_partition():
    """create_answer_log_partition 建月分区,该月作答事件落入命名分区(非默认)。"""
    stu = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            await create_answer_log_partition(db, 2026, 7)
            await db.commit()
        async with _async_session_factory() as db:
            log_id = uuid.uuid4()
            db.add(AnswerLog(id=log_id, student_id=stu, q_scope="platform",
                             question_id=uuid.uuid4(), is_correct=False,
                             answered_at=datetime(2026, 7, 10, tzinfo=timezone.utc)))
            await db.commit()
        async with _async_session_factory() as db:
            # 该行的物理分区 = answer_log_202607(用 tableoid::regclass 反查)
            part = (await db.execute(text(
                "SELECT tableoid::regclass::text FROM answer_log WHERE id = :i"
            ), {"i": str(log_id)})).scalar_one()
            assert part == answer_log_partition_name(2026, 7)
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(stu)})
            await db.commit()


def test_scoped_helper_filters():
    """scoped() 给查询强制加 scope(+owner)过滤条件。"""
    stu = uuid.uuid4()
    stmt = scoped(select(UploadedQuestion), UploadedQuestion.owner_scope, "student",
                  UploadedQuestion.owner_id, stu)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "owner_scope" in compiled and "owner_id" in compiled
    # 平台域只读引用:只过 scope,不带 owner
    stmt2 = scoped(select(Passage), Passage.scope, "platform")
    assert "scope" in str(stmt2.compile())


async def _cleanup(node_id, stu):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(stu)})
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(stu)})
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(stu)})
        await db.execute(text("DELETE FROM platform_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM uploaded_question_kp WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(stu)})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM passage WHERE text LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()
