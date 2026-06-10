"""整卷 service 测试（D-089 / M4）：建卷 + 后台管线 + 详情。"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory as _async_session_factory
from app.models.d1_users import User
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.services import user_paper_service
from app.services.ocr_service import OcrResult

# 整卷拆题 dev mock 文字：两道题（27/28），学生手写答案均为 B。
# 经 paper_split_service._dev_mock_split（deepseek dev 模式）确定性拆出 2 题。
_MOCK_PRINTED = (
    "27. The teacher asked the students to _____ their homework on time.\n"
    "A. hand in  B. hand out  C. hand over  D. hand up\n"
    "28. She _____ in Beijing for three years before she moved to Shanghai.\n"
    "A. lived  B. had lived  C. has lived  D. lives"
)
_MOCK_HANDWRITTEN = "27. B\n28. B"


async def _fake_run_ocr(image_url: str) -> OcrResult:
    """替身：避免真实豆包 Vision 网络请求，返回确定性 OCR 文字。"""
    return OcrResult(printed_text=_MOCK_PRINTED, handwritten_text=_MOCK_HANDWRITTEN)


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _async_session_factory() as s:
        try:
            yield s
        finally:
            await s.rollback()


async def _make_user(s: AsyncSession) -> User:
    # User 模型字段名是 openid（非 wx_openid）；role 为 user_role_enum（"student"）。
    u = User(
        id=uuid.uuid4(),
        openid=f"openid-{uuid.uuid4().hex[:8]}",
        role="student",
    )
    s.add(u)
    await s.commit()
    return u


@pytest.mark.asyncio
async def test_create_paper_sets_pending(db_session: AsyncSession):
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg", "https://mock/p2.jpg"],
        title="期中卷",
    )
    assert paper.id is not None
    assert paper.ocr_status == "pending"
    assert paper.title == "期中卷"
    assert len(paper.source_image_urls) == 2


@pytest.mark.asyncio
async def test_run_pipeline_populates_questions(db_session: AsyncSession):
    """dev mock：跑管线后 ocr_status=completed 且拆出 2 题。"""
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()

    # patch 视觉识别函数，避免真实豆包 Vision 网络请求（mock 图片 URL 无法解析）。
    with patch("app.services.ocr_service.run_ocr", _fake_run_ocr):
        await user_paper_service.run_paper_pipeline(paper.id)

    async with _async_session_factory() as s:
        reloaded = await s.get(UserUploadedPaper, paper.id)
        assert reloaded.ocr_status == "completed"
        qs = (await s.execute(
            select(UserPaperQuestion).where(UserPaperQuestion.user_paper_id == paper.id)
        )).scalars().all()
        assert len(qs) == 2
        nos = sorted(q.question_no for q in qs)
        assert nos == ["27", "28"]
        assert all(q.student_answer == "B" for q in qs)


@pytest.mark.asyncio
async def test_get_paper_detail_returns_questions(db_session: AsyncSession):
    user = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=user.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()
    with patch("app.services.ocr_service.run_ocr", _fake_run_ocr):
        await user_paper_service.run_paper_pipeline(paper.id)

    detail = await user_paper_service.get_paper_detail(
        db_session, paper_id=paper.id, student_id=user.id
    )
    assert detail is not None
    assert detail.question_count == 2
    assert len(detail.questions) == 2


@pytest.mark.asyncio
async def test_get_paper_detail_wrong_owner_returns_none(db_session: AsyncSession):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    paper = await user_paper_service.create_paper(
        db_session,
        student_id=owner.id,
        source_image_urls=["https://mock/p1.jpg"],
        title=None,
    )
    await db_session.commit()

    detail = await user_paper_service.get_paper_detail(
        db_session, paper_id=paper.id, student_id=other.id
    )
    assert detail is None
