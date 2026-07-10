"""TDD: adaptive_question_service — 按薄弱知识点智能出题。

Red-Green-Refactor 顺序：
  1. 写此测试
  2. 跑 pytest → 必须 RED（ImportError / AttributeError）
  3. 写 adaptive_question_service.py 最小实现
  4. 跑 pytest → GREEN
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimPracticeRecord, SimulatedQuestion


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        openid=f"test_openid_{uuid.uuid4().hex[:8]}",
        nickname="TDD学生",
        role="student",
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


def _make_kp(name: str, desc: str = "") -> KnowledgePoint:
    return KnowledgePoint(
        id=uuid.uuid4(),
        code=f"TST_{uuid.uuid4().hex[:6]}",
        name=name,
        category="grammar",
        description=desc or None,
        applicable_grades=["小学5年级"],
        applicable_textbooks=["译林版"],
    )


@pytest_asyncio.fixture
async def kp(db: AsyncSession) -> KnowledgePoint:
    kp = _make_kp("现在完成时", "表示过去发生对现在有影响的动作")
    db.add(kp)
    await db.flush()
    return kp


@pytest_asyncio.fixture
async def kp2(db: AsyncSession) -> KnowledgePoint:
    kp = _make_kp("被动语态", "表示主语是动作的承受者")
    db.add(kp)
    await db.flush()
    return kp


@pytest_asyncio.fixture
async def wrong_question_with_analysis(
    db: AsyncSession, student: User, kp: KnowledgePoint
) -> WrongQuestion:
    """造一道错题 + AI 分析，让诊断数据中有薄弱知识点。"""
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student.id,
        question_type="单选",
        question_text="He ___ to school yesterday.",
        correct_answer="went",
        student_answer="go",
        source_image_url="v2-practice",
        is_mastered=False,
    )
    db.add(wq)
    await db.flush()

    ai = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq.id,
        student_id=student.id,
        llm_provider="deepseek",
        error_types=["时态错误"],
        knowledge_points=[kp.name],
        diagnosis="时态使用错误",
        suggestions="注意过去式的使用",
        tokens_used=100,
    )
    db.add(ai)
    await db.flush()
    return wq


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_adaptive_set_returns_questions(
    db: AsyncSession,
    student: User,
    kp: KnowledgePoint,
    wrong_question_with_analysis,
):
    """有薄弱知识点时，应返回至少1道题。"""
    from app.services import adaptive_question_service

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )

    assert result.questions, "薄弱点有数据时必须返回题目"
    assert len(result.questions) <= 5
    assert result.weak_kp_names, "必须返回薄弱知识点名称列表"


@pytest.mark.asyncio
async def test_get_adaptive_set_no_data_returns_empty(
    db: AsyncSession,
    student: User,
):
    """没有任何错题时，返回空题集（不报错）。"""
    from app.services import adaptive_question_service

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )

    assert result.questions == []
    assert result.weak_kp_names == []


@pytest.mark.asyncio
async def test_get_adaptive_set_excludes_already_done(
    db: AsyncSession,
    student: User,
    kp: KnowledgePoint,
    wrong_question_with_analysis,
):
    """已做过的题（sim_practice_records 里有记录）不应重复出现。"""
    from app.services import adaptive_question_service

    # 直接建一道仿真题（question_service.persist_questions 已退役，改直插模型）
    sq = SimulatedQuestion(
        id=uuid.uuid4(),
        knowledge_point_id=kp.id,
        question_type="单选",
        stem="占位题干",
        options=["A. x", "B. y", "C. z", "D. w"],
        answer="B",
        explanation="占位解析",
        difficulty=1,
        status="published",
    )
    db.add(sq)
    await db.flush()
    saved = [sq]

    # 记录该学生已做过这道题
    rec = SimPracticeRecord(
        id=uuid.uuid4(),
        student_id=student.id,
        simulated_question_id=saved[0].id,
        knowledge_point_id=kp.id,
        is_correct=False,
        user_answer="wrong",
    )
    db.add(rec)
    await db.flush()

    # 如果题库只有这1道且已做过，结果应该是0道（或由 AI 新生成的题）
    # 此测试只验证"已做过"的那道题 id 不在结果里
    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )
    done_ids = {saved[0].id}
    result_ids = {q.id for q in result.questions}
    assert not (done_ids & result_ids), "已做过的题不应再次出现"


@pytest.mark.asyncio
async def test_get_adaptive_set_respects_total_limit(
    db: AsyncSession,
    student: User,
    kp: KnowledgePoint,
    kp2: KnowledgePoint,
    wrong_question_with_analysis,
):
    """返回题目数量不超过 total 参数。"""
    from app.services import adaptive_question_service

    # 给 kp2 也加错题记录
    wq2 = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student.id,
        question_type="填空",
        question_text="The window ___ broken.",
        correct_answer="was",
        student_answer="is",
        source_image_url="v2-practice",
        is_mastered=False,
    )
    db.add(wq2)
    await db.flush()
    ai2 = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq2.id,
        student_id=student.id,
        llm_provider="deepseek",
        error_types=["语态错误"],
        knowledge_points=[kp2.name],
        diagnosis="语态使用错误",
        suggestions="注意被动语态",
        tokens_used=100,
    )
    db.add(ai2)
    await db.flush()

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=3
    )
    assert len(result.questions) <= 3


def test_to_enum_type_maps_fill_types():
    """物化题型映射:客观填空类→enum「填空」;选择类如实继承;未知/主观→兜底单选。"""
    from app.services.adaptive_question_service import _to_enum_type
    assert _to_enum_type("动词填空") == "填空"
    assert _to_enum_type("词汇运用") == "填空"
    assert _to_enum_type("短文填空") == "填空"
    assert _to_enum_type("完型") == "完型"
    assert _to_enum_type("阅读") == "阅读"
    assert _to_enum_type("单选") == "单选"
    assert _to_enum_type(None) == "单选"
