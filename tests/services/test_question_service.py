"""question_service 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.services import question_ai_service, question_service
from app.services.auth_service import upsert_user


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def seeded_kp(db_session):
    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=f"test-kp-{uuid.uuid4().hex[:6]}",
        name="测试 KP",
        category="grammar",
        description="测试用",
        applicable_grades=["小学5年级"],
        applicable_textbooks=["译林版"],
    )
    db_session.add(kp)
    await db_session.flush()
    return kp


@pytest.mark.asyncio
async def test_persist_questions_creates_5_rows(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    assert len(created) == 5

    rows = (await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all()
    assert len(rows) >= 5


@pytest.mark.asyncio
async def test_persist_idempotent(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()
    cnt1 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())

    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()
    cnt2 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())
    assert cnt1 == cnt2


@pytest.mark.asyncio
async def test_grading_single_choice_strict_equal(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem="X", options=["A", "B", "C", "D"],
        answer="B", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="B",
    )
    assert r1.correct is True
    assert r1.wrong_question_id is None

    r2 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="A",
    )
    assert r2.correct is False
    assert r2.correct_answer == "B"
    assert r2.wrong_question_id is not None


@pytest.mark.asyncio
async def test_grading_fill_case_insensitive_multi_answer(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="填空", stem="X", options=None,
        answer="goes|go", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="goes")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="GO ")
    assert r2.correct is True
    r3 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="went")
    assert r3.correct is False


@pytest.mark.asyncio
async def test_grading_judge_strict(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="判断", stem="X", options=None,
        answer="错", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="错")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="对")
    assert r2.correct is False


@pytest.mark.asyncio
async def test_wrong_attempt_creates_wrong_question_with_kp_link(db_session, seeded_kp):
    """错题应自动写 wrong_questions + wrong_question_knowledge_points + 映射 question_type 到合法 enum。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="判断", stem="判断题干样本", options=None,
        answer="对", explanation="解析", difficulty=2, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="错",
    )
    assert r.wrong_question_id is not None

    wq = (await db_session.execute(
        select(WrongQuestion).where(WrongQuestion.id == r.wrong_question_id)
    )).scalar_one()
    assert wq.student_id == user.id
    assert "判断题干样本" in (wq.question_text or "")
    assert wq.student_answer == "错"
    assert wq.correct_answer == "对"
    # 判断映射到 enum "其他"
    assert str(wq.question_type) == "其他"
    # source_image_url 非空（满足 NOT NULL）
    assert wq.source_image_url

    # KP 链接也已建
    link = (await db_session.execute(
        select(WrongQuestionKnowledgePoint).where(
            WrongQuestionKnowledgePoint.wrong_question_id == wq.id,
            WrongQuestionKnowledgePoint.knowledge_point_id == seeded_kp.id,
        )
    )).scalar_one_or_none()
    assert link is not None
