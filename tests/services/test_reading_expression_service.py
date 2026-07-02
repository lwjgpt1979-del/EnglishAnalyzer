"""阅读表达批改 service 测试（P2a，dev-mock 离线确定）。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import AnswerLog, StudentKp
from app.services import platform_question_service as pqs
from app.services import reading_expression_service as res


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"re_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


async def _seed_re_question(s, node_id, *, answer="before breakfast") -> uuid.UUID:
    r = await pqs.import_real_question(
        s, stem="When does Tom run?", answer=answer,
        question_type="阅读", section="阅读表达", status="published")
    await pqs.attach_node(s, r.question_id, node_id)
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_grade_hit_when_reference_matched():
    r = await res.grade_reading_expression(
        question="When does Tom run?", reference_answer="before breakfast",
        student_answer="He runs before breakfast every morning.", full_score=4)
    assert r["points"] and r["points"][0]["hit"] is True
    assert r["total"] == 4 and r["full"] == 4
    assert r["content_score"] == 4


@pytest.mark.asyncio
async def test_grade_partial_when_short_unmatched():
    r = await res.grade_reading_expression(
        question="Q", reference_answer="a specific long reference point about the plot",
        student_answer="no", full_score=4)
    assert r["points"][0]["hit"] is False
    assert r["total"] == 2  # full - 2


@pytest.mark.asyncio
async def test_grade_empty_answer_returns_zero():
    r = await res.grade_reading_expression(
        question="Q", reference_answer="ref", student_answer="   ", full_score=6)
    assert r["total"] == 0 and r["full"] == 6 and r["points"] == []


@pytest.mark.asyncio
async def test_grade_by_question_records_wrong_on_miss(db_session):
    """按 question_id 判分:miss → answer_log(错)+ student_kp.wrong_count 计错(闭环)。"""
    sid = await _student(db_session)
    node = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.axis == "knowledge").limit(1))).scalar_one()
    qid = await _seed_re_question(db_session, node.id)
    r = await res.grade_platform_question(
        db_session, student_id=sid, question_id=qid, student_answer="no")
    assert r["is_correct"] is False
    logs = (await db_session.execute(
        select(AnswerLog).where(AnswerLog.student_id == sid,
                                AnswerLog.question_id == qid))).scalars().all()
    assert len(logs) == 1 and logs[0].is_correct is False and logs[0].node_id == node.id
    skp = (await db_session.execute(
        select(StudentKp).where(StudentKp.student_id == sid,
                                StudentKp.node_id == node.id))).scalar_one()
    assert skp.wrong_count >= 1


@pytest.mark.asyncio
async def test_list_practice_questions_never_leaks_answer(db_session):
    """按题练列表:每项只含 id/stem/passage/full_score,绝不下发参考答案(防作弊)。"""
    node = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.axis == "knowledge").limit(1))).scalar_one()
    await _seed_re_question(db_session, node.id)
    items = await res.list_practice_questions(db_session, limit=20)
    assert all(set(it.keys()) == {"id", "stem", "passage", "full_score"} for it in items)
    assert all("answer" not in it and "reference_answer" not in it for it in items)


@pytest.mark.asyncio
async def test_grade_by_question_pass_on_hit(db_session):
    """作答命中参考答案 → is_correct True、answer_log 记对。"""
    sid = await _student(db_session)
    node = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.axis == "knowledge").limit(1))).scalar_one()
    qid = await _seed_re_question(db_session, node.id)
    r = await res.grade_platform_question(
        db_session, student_id=sid, question_id=qid,
        student_answer="He runs before breakfast every morning.")
    assert r["is_correct"] is True
    log = (await db_session.execute(
        select(AnswerLog).where(AnswerLog.student_id == sid,
                                AnswerLog.question_id == qid))).scalar_one()
    assert log.is_correct is True
