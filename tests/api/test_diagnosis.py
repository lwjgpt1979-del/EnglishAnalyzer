import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.schemas.diagnosis import (
    DailyActivity,
    DiagnosisReport,
    ErrorTypeCount,
    KnowledgePointCount,
)
from app.services.auth_service import upsert_user
from app.services.diagnosis_service import get_diagnosis_report

# ── Schema 单元测试（同步）────────────────────────────────────────────────────


def test_error_type_count_schema():
    etc = ErrorTypeCount(error_type="语法错误", count=5)
    assert etc.error_type == "语法错误"
    assert etc.count == 5


def test_knowledge_point_count_schema():
    kpc = KnowledgePointCount(knowledge_point="现在完成时", count=3)
    assert kpc.knowledge_point == "现在完成时"
    assert kpc.count == 3


def test_daily_activity_schema():
    da = DailyActivity(date="2026-05-26", count=3)
    assert da.date == "2026-05-26"
    assert da.count == 3


def test_diagnosis_report_schema_empty():
    report = DiagnosisReport(
        total_questions=0,
        total_analyzed=0,
        mastered_count=0,
        mastery_rate=0.0,
        top_error_types=[],
        top_weak_knowledge_points=[],
        question_type_distribution={},
        difficulty_distribution={},
        recent_daily_activity=[],
        top_suggestions=[],
    )
    assert report.total_questions == 0
    assert report.mastery_rate == 0.0
    assert report.top_error_types == []


def test_diagnosis_report_schema_with_data():
    report = DiagnosisReport(
        total_questions=10,
        total_analyzed=8,
        mastered_count=3,
        mastery_rate=0.3,
        top_error_types=[ErrorTypeCount(error_type="语法错误", count=4)],
        top_weak_knowledge_points=[KnowledgePointCount(knowledge_point="现在完成时", count=3)],
        question_type_distribution={"单选": 5, "完型": 3, "阅读": 2},
        difficulty_distribution={3: 6, 4: 4},
        recent_daily_activity=[DailyActivity(date="2026-05-26", count=2)],
        top_suggestions=["建议多练习时态题"],
    )
    assert report.total_analyzed == 8
    assert report.mastery_rate == 0.3
    assert report.top_error_types[0].error_type == "语法错误"


# ── Service 集成测试（异步，需要真实 DB）──────────────────────────────────────


@pytest_asyncio.fixture
async def db_session():
    # 使用私有工厂直接创建 session，避免 get_db 中的 RLS 注入影响 service 层单测。
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_student(db_session):
    user = await upsert_user(db_session, openid=f"diag_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_get_diagnosis_report_empty(db_session, test_student):
    """无错题时返回全零报告，recent_daily_activity 固定30天。"""
    report = await get_diagnosis_report(db_session, student_id=test_student.id)
    assert report.total_questions == 0
    assert report.total_analyzed == 0
    assert report.mastered_count == 0
    assert report.mastery_rate == 0.0
    assert report.top_error_types == []
    assert report.top_weak_knowledge_points == []
    assert report.question_type_distribution == {}
    assert report.difficulty_distribution == {}
    assert len(report.recent_daily_activity) == 30
    assert report.top_suggestions == []


@pytest.mark.asyncio
async def test_get_diagnosis_report_with_data(db_session, test_student):
    """有错题+分析时，聚合结果正确。"""
    # 创建2道错题
    wq1 = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img1.jpg",
        question_type="单选",
        difficulty=3,
        is_mastered=True,
    )
    wq2 = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img2.jpg",
        question_type="完型",
        difficulty=4,
        is_mastered=False,
    )
    db_session.add_all([wq1, wq2])
    await db_session.flush()

    # 为 wq1 创建 AI 分析
    analysis = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq1.id,
        student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误", "时态错误"],
        knowledge_points=["现在完成时", "过去时"],
        diagnosis="该生对时态掌握不牢。",
        suggestions="建议复习时态用法，多做专项练习。",
        confidence_score=0.85,
        tokens_used=512,
    )
    db_session.add(analysis)
    await db_session.flush()

    report = await get_diagnosis_report(db_session, student_id=test_student.id)

    assert report.total_questions == 2
    assert report.total_analyzed == 1
    assert report.mastered_count == 1
    assert report.mastery_rate == 0.5
    assert len(report.top_error_types) == 2
    assert {etc.error_type for etc in report.top_error_types} == {"语法错误", "时态错误"}
    assert len(report.top_weak_knowledge_points) == 2
    assert report.question_type_distribution == {"单选": 1, "完型": 1}
    assert report.difficulty_distribution == {3: 1, 4: 1}
    assert len(report.recent_daily_activity) == 30
    assert len(report.top_suggestions) == 1
    assert report.top_suggestions[0] == "建议复习时态用法，多做专项练习。"


@pytest.mark.asyncio
async def test_get_diagnosis_report_error_type_ordering(db_session, test_student):
    """error_types 按频次降序排列。"""
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=test_student.id,
        source_image_url="https://example.com/img.jpg",
        is_mastered=False,
    )
    db_session.add(wq)
    await db_session.flush()

    # 分析1：语法错误 + 词汇错误
    a1 = AiAnalysis(
        id=uuid.uuid4(), wrong_question_id=wq.id, student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误", "词汇错误"],
        knowledge_points=["介词"],
        diagnosis="d", suggestions="s1",
        confidence_score=0.8, tokens_used=100,
    )
    wq2 = WrongQuestion(
        id=uuid.uuid4(), student_id=test_student.id,
        source_image_url="https://example.com/img2.jpg", is_mastered=False,
    )
    db_session.add(wq2)
    await db_session.flush()

    # 分析2：语法错误（重复出现，使其排第一）
    a2 = AiAnalysis(
        id=uuid.uuid4(), wrong_question_id=wq2.id, student_id=test_student.id,
        llm_provider="claude",
        error_types=["语法错误"],
        knowledge_points=["主谓一致"],
        diagnosis="d2", suggestions="s2",
        confidence_score=0.9, tokens_used=80,
    )
    db_session.add_all([a1, a2])
    await db_session.flush()

    report = await get_diagnosis_report(db_session, student_id=test_student.id)

    # 语法错误出现2次，应排第一
    assert report.top_error_types[0].error_type == "语法错误"
    assert report.top_error_types[0].count == 2
