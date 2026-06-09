"""诊断报告整卷错题 KP 联动 TDD 测试。

整卷错题（user_paper_questions.is_wrong=True）的 knowledge_point 应计入
_aggregate_structured_dimensions 返回的 kp_dimension（accuracy=0）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d13_v2_user_papers import (
    UserPaperQuestion,
    UserPaperQuestionKnowledgePoint,
    UserUploadedPaper,
)
from app.models.d4_knowledge import KnowledgePoint


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


def _make_kp(name: str) -> KnowledgePoint:
    return KnowledgePoint(
        id=uuid.uuid4(),
        code=f"TST_{uuid.uuid4().hex[:6]}",
        name=name,
        category="grammar",
        applicable_grades=["小学5年级"],
        applicable_textbooks=["译林版"],
    )


@pytest_asyncio.fixture
async def student_id(db: AsyncSession) -> uuid.UUID:
    """创建真实 User 以满足 FK 约束。"""
    sid = uuid.uuid4()
    db.add(User(id=sid, openid=f"diag_{sid.hex[:8]}", role="student", is_active=True))
    await db.flush()
    return sid


@pytest_asyncio.fixture
async def seed_paper_kp(db: AsyncSession, student_id: uuid.UUID):
    """整卷错题 + KP 关联（被动语态）。"""
    kp = _make_kp("被动语态")
    db.add(kp)
    await db.flush()
    paper = UserUploadedPaper(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_urls=["https://x.com/p.jpg"],
        ocr_status="completed",
    )
    db.add(paper)
    await db.flush()
    q = UserPaperQuestion(
        id=uuid.uuid4(),
        user_paper_id=paper.id,
        stem="被动句翻译",
        is_wrong=True,
        question_type="单选",
    )
    db.add(q)
    await db.flush()
    link = UserPaperQuestionKnowledgePoint(
        user_paper_question_id=q.id,
        knowledge_point_id=kp.id,
    )
    db.add(link)
    await db.flush()
    return {"kp": kp, "question": q}


@pytest.mark.asyncio
async def test_diagnosis_kp_dim_includes_paper_kp(db, student_id, seed_paper_kp):
    """整卷错题的 KP 出现在 kp_dimension，accuracy=0.0。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions

    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)

    kp_ids = [item.knowledge_point_id for item in kp_dim]
    assert seed_paper_kp["kp"].id in kp_ids

    item = next(i for i in kp_dim if i.knowledge_point_id == seed_paper_kp["kp"].id)
    assert item.accuracy == 0.0
    assert item.attempts >= 1
    assert item.correct == 0


@pytest.mark.asyncio
async def test_diagnosis_kp_dim_no_paper_wrong_returns_empty(db, student_id):
    """没有任何练习记录时 kp_dimension 为空列表。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions

    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)
    assert kp_dim == []


@pytest.mark.asyncio
async def test_diagnosis_paper_correct_question_not_counted(db, student_id):
    """整卷答对的题（is_wrong=False）不计入 kp_dimension。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions

    kp = _make_kp("一般现在时")
    db.add(kp)
    await db.flush()
    paper = UserUploadedPaper(
        id=uuid.uuid4(), student_id=student_id,
        source_image_urls=["https://x.com/p2.jpg"], ocr_status="completed",
    )
    db.add(paper)
    await db.flush()
    q = UserPaperQuestion(
        id=uuid.uuid4(), user_paper_id=paper.id, stem="正确题",
        is_wrong=False, question_type="单选",
    )
    db.add(q)
    await db.flush()
    link = UserPaperQuestionKnowledgePoint(
        user_paper_question_id=q.id, knowledge_point_id=kp.id,
    )
    db.add(link)
    await db.flush()

    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)
    # 答对题的 KP 不应出现
    kp_ids = [item.knowledge_point_id for item in kp_dim]
    assert kp.id not in kp_ids
