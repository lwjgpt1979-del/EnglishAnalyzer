import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
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


# ── API 集成测试 ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"diag_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, f"wx-login failed: {resp.text}"
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_requires_auth(client: AsyncClient):
    """未登录返回 401。"""
    resp = await client.get("/api/v1/diagnosis/report")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_empty(client: AsyncClient, auth_headers):
    """新用户无数据时，返回全零报告 + 30天活跃度数组。"""
    resp = await client.get("/api/v1/diagnosis/report", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total_questions"] == 0
    assert data["total_analyzed"] == 0
    assert data["mastered_count"] == 0
    assert data["mastery_rate"] == 0.0
    assert data["top_error_types"] == []
    assert data["top_weak_knowledge_points"] == []
    assert data["question_type_distribution"] == {}
    assert len(data["recent_daily_activity"]) == 30
    assert data["top_suggestions"] == []


@pytest.mark.asyncio
async def test_get_diagnosis_report_api_structure(client: AsyncClient, auth_headers):
    """响应结构正确：所有字段存在，类型正确。"""
    resp = await client.get("/api/v1/diagnosis/report", headers=auth_headers)
    data = resp.json()["data"]
    # 所有必需字段存在
    assert "total_questions" in data
    assert "total_analyzed" in data
    assert "mastered_count" in data
    assert "mastery_rate" in data
    assert "top_error_types" in data
    assert "top_weak_knowledge_points" in data
    assert "question_type_distribution" in data
    assert "difficulty_distribution" in data
    assert "recent_daily_activity" in data
    assert "top_suggestions" in data
    # recent_daily_activity 每条有 date 和 count
    assert all("date" in d and "count" in d for d in data["recent_daily_activity"])


# ── M3 学情报告结构化维度（按知识点 / 按学期，D-094）──────────────────────────

from app.schemas.diagnosis import KpDimensionItem, SemesterDimensionItem


def test_kp_dimension_item_schema():
    it = KpDimensionItem(
        knowledge_point_id=uuid.uuid4(),
        knowledge_point_name="一般过去时",
        category="grammar",
        attempts=4,
        correct=1,
        accuracy=0.25,
    )
    assert it.accuracy == 0.25
    assert it.category == "grammar"


def test_semester_dimension_item_schema():
    it = SemesterDimensionItem(
        grade="七年级", semester="上", label="七年级上",
        attempts=10, correct=6, accuracy=0.6,
    )
    assert it.label == "七年级上"


def test_diagnosis_report_dimensions_default_empty():
    """新维度字段默认空列表，保持向后兼容。"""
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
    assert report.kp_dimension == []
    assert report.semester_dimension == []


async def _make_kp_with_unit(db_session, *, accuracy_attempts, student_id):
    """建 KP + 单元 + 关联，并按 accuracy_attempts=[(is_correct), ...] 写练习记录。"""
    from app.models.d4_knowledge import (
        CurriculumUnit, KnowledgePoint, UnitKnowledgePoint,
    )
    from app.models.d12_v2_exams import SimPracticeRecord, SimulatedQuestion

    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=f"KP_{uuid.uuid4().hex[:8]}",
        name="一般过去时",
        category="grammar",
        applicable_grades=["七年级"],
        applicable_textbooks=["人教版"],
    )
    db_session.add(kp)
    unit = CurriculumUnit(
        id=uuid.uuid4(),
        textbook_version="人教版",
        grade="七年级",
        semester="上",
        unit_no=1,
        unit_title="Unit 1",
    )
    db_session.add(unit)
    await db_session.flush()
    db_session.add(UnitKnowledgePoint(unit_id=unit.id, knowledge_point_id=kp.id))
    # 一道仿真题（练习记录 FK 需要）
    sq = SimulatedQuestion(
        id=uuid.uuid4(),
        knowledge_point_id=kp.id,
        question_type="单选",
        stem="She ___ to school yesterday.",
        options=["go", "goes", "went", "going"],
        answer="C",
        explanation="过去时",
        difficulty=2,
        status="published",
    )
    db_session.add(sq)
    await db_session.flush()
    for ok in accuracy_attempts:
        db_session.add(SimPracticeRecord(
            id=uuid.uuid4(),
            student_id=student_id,
            simulated_question_id=sq.id,
            knowledge_point_id=kp.id,
            is_correct=ok,
            user_answer="C" if ok else "A",
        ))
    await db_session.flush()
    return kp, unit


@pytest.mark.asyncio
async def test_diagnosis_structured_dimensions_with_data(db_session, test_student):
    # 4 次作答，1 对 3 错 → accuracy 0.25
    await _make_kp_with_unit(
        db_session, accuracy_attempts=[True, False, False, False],
        student_id=test_student.id,
    )
    report = await get_diagnosis_report(db_session, student_id=test_student.id)

    assert len(report.kp_dimension) == 1
    kp_item = report.kp_dimension[0]
    assert kp_item.knowledge_point_name == "一般过去时"
    assert kp_item.attempts == 4
    assert kp_item.correct == 1
    assert kp_item.accuracy == 0.25

    assert len(report.semester_dimension) == 1
    sem_item = report.semester_dimension[0]
    assert sem_item.label == "七年级上"
    assert sem_item.attempts == 4
    assert sem_item.correct == 1
    assert sem_item.accuracy == 0.25


@pytest.mark.asyncio
async def test_diagnosis_structured_dimensions_empty(db_session, test_student):
    """无练习记录时两个维度为空。"""
    report = await get_diagnosis_report(db_session, student_id=test_student.id)
    assert report.kp_dimension == []
    assert report.semester_dimension == []
