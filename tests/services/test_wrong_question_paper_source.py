"""wrong_question_service paper source TDD 测试。

整卷错题（user_paper_questions.is_wrong=True）由独立的
list_paper_wrongs() service 函数处理，返回 PaperWrongItem 列表。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def student_id(db: AsyncSession) -> uuid.UUID:
    """创建真实 User 以满足 FK 约束。"""
    sid = uuid.uuid4()
    db.add(User(
        id=sid,
        openid=f"test_paper_{sid.hex[:8]}",
        role="student",
        is_active=True,
    ))
    await db.flush()
    return sid


@pytest_asyncio.fixture
async def seed_paper_questions(db: AsyncSession, student_id: uuid.UUID):
    """1 个整卷，3 道题：2 错（is_wrong=True），1 对。"""
    paper = UserUploadedPaper(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_urls=["https://example.com/p1.jpg"],
        ocr_status="completed",
    )
    db.add(paper)
    await db.flush()  # 先持久化 paper，确保 FK 引用存在
    wrong1 = UserPaperQuestion(
        id=uuid.uuid4(),
        user_paper_id=paper.id,
        stem="题目A",
        is_wrong=True,
        question_type="单选",
    )
    wrong2 = UserPaperQuestion(
        id=uuid.uuid4(),
        user_paper_id=paper.id,
        stem="题目B",
        is_wrong=True,
        question_type="填空",
    )
    correct1 = UserPaperQuestion(
        id=uuid.uuid4(),
        user_paper_id=paper.id,
        stem="题目C",
        is_wrong=False,
        question_type="单选",
    )
    db.add_all([wrong1, wrong2, correct1])
    await db.flush()
    return {"paper": paper, "wrong1": wrong1, "wrong2": wrong2, "correct1": correct1}


@pytest.mark.asyncio
async def test_list_paper_wrongs_only_is_wrong_true(db, student_id, seed_paper_questions):
    """只返回 is_wrong=True 的题，答对的题目不出现。"""
    from app.services.wrong_question_service import list_paper_wrongs

    items, total = await list_paper_wrongs(db, student_id=student_id, skip=0, limit=20)
    assert total == 2
    assert len(items) == 2
    stems = [i.stem for i in items]
    assert "题目A" in stems
    assert "题目B" in stems
    assert "题目C" not in stems


@pytest.mark.asyncio
async def test_list_paper_wrongs_source_label(db, student_id, seed_paper_questions):
    """每条记录的 source_label 为 '整卷'。"""
    from app.services.wrong_question_service import list_paper_wrongs

    items, _ = await list_paper_wrongs(db, student_id=student_id, skip=0, limit=20)
    for item in items:
        assert item.source_label == "整卷"


@pytest.mark.asyncio
async def test_list_paper_wrongs_is_mastered_false(db, student_id, seed_paper_questions):
    """整卷错题 is_mastered 始终 False（不支持手动掌握）。"""
    from app.services.wrong_question_service import list_paper_wrongs

    items, _ = await list_paper_wrongs(db, student_id=student_id, skip=0, limit=20)
    for item in items:
        assert item.is_mastered is False


@pytest.mark.asyncio
async def test_list_paper_wrongs_limit(db, student_id, seed_paper_questions):
    """limit 参数生效，最多返回 1 条。"""
    from app.services.wrong_question_service import list_paper_wrongs

    items, total = await list_paper_wrongs(db, student_id=student_id, skip=0, limit=1)
    assert len(items) == 1
    assert total == 2  # total 仍为全量


@pytest.mark.asyncio
async def test_list_paper_wrongs_empty_for_other_student(db, seed_paper_questions):
    """其他学生的整卷不出现。"""
    from app.services.wrong_question_service import list_paper_wrongs

    other = uuid.uuid4()
    items, total = await list_paper_wrongs(db, student_id=other, skip=0, limit=20)
    assert total == 0
    assert items == []
