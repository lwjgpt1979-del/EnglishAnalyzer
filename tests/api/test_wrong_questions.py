from app.core.config import settings


def test_settings_has_anthropic_api_key():
    """settings 必须有 anthropic_api_key 字段（值可为 placeholder）。"""
    assert hasattr(settings, "anthropic_api_key")
    assert isinstance(settings.anthropic_api_key, str)


import uuid
from datetime import datetime, timezone

from app.schemas.wrong_questions import (
    AiAnalysisOut,
    MarkMasteredRequest,
    WrongQuestionCreate,
    WrongQuestionListOut,
    WrongQuestionOut,
)


def test_wrong_question_create_requires_source_image_url():
    wq = WrongQuestionCreate(source_image_url="https://cdn.example.com/img.jpg")
    assert wq.source_image_url == "https://cdn.example.com/img.jpg"
    assert wq.question_text is None
    assert wq.tags is None


def test_wrong_question_out_serializes():
    now = datetime.now(timezone.utc)
    out = WrongQuestionOut(
        id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        source_image_url="https://cdn.example.com/img.jpg",
        question_text="What is the correct tense here?",
        student_answer="I go to school yesterday",
        correct_answer="I went to school yesterday",
        question_type="单选",
        difficulty=2,
        tags=["时态", "过去式"],
        is_mastered=False,
        mastered_at=None,
        created_at=now,
        updated_at=now,
    )
    assert out.is_mastered is False
    assert out.tags == ["时态", "过去式"]


def test_ai_analysis_out_serializes():
    now = datetime.now(timezone.utc)
    out = AiAnalysisOut(
        id=str(uuid.uuid4()),
        wrong_question_id=str(uuid.uuid4()),
        llm_provider="claude",
        error_types=["时态错误"],
        knowledge_points=["一般过去时"],
        diagnosis="学生混淆了一般现在时和一般过去时。",
        suggestions="加强时态练习，重点复习过去时标志词。",
        confidence_score=0.92,
        tokens_used=312,
        created_at=now,
    )
    assert out.llm_provider == "claude"
    assert out.confidence_score == 0.92


import pytest
import pytest_asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.schemas.wrong_questions import WrongQuestionCreate
from app.services.wrong_question_service import (
    create_wrong_question,
    get_wrong_question,
    list_wrong_questions,
    mark_mastered,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_student(db_session):
    from app.services.auth_service import upsert_user
    user = await upsert_user(db_session, openid=f"wq_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_create_wrong_question(db_session, test_student):
    data = WrongQuestionCreate(
        source_image_url="https://cdn.example.com/test.jpg",
        question_text="She __ to school every day.",
        student_answer="go",
        correct_answer="goes",
        question_type="单选",
        difficulty=2,
        tags=["主谓一致"],
    )
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    assert wq.id is not None
    assert wq.student_id == test_student.id
    assert wq.question_text == "She __ to school every day."
    assert wq.tags == ["主谓一致"]
    assert wq.is_mastered is False


@pytest.mark.asyncio
async def test_get_wrong_question_owned(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/a.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    found = await get_wrong_question(db_session, wq_id=wq.id, student_id=test_student.id)
    assert found is not None
    assert found.id == wq.id


@pytest.mark.asyncio
async def test_get_wrong_question_not_owned_returns_none(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/b.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    other_id = uuid.uuid4()
    found = await get_wrong_question(db_session, wq_id=wq.id, student_id=other_id)
    assert found is None


@pytest.mark.asyncio
async def test_list_wrong_questions(db_session, test_student):
    for i in range(3):
        await create_wrong_question(
            db_session,
            student_id=test_student.id,
            data=WrongQuestionCreate(source_image_url=f"https://cdn.example.com/{i}.jpg"),
        )
    items, total = await list_wrong_questions(
        db_session, student_id=test_student.id, skip=0, limit=10
    )
    assert total >= 3
    assert len(items) >= 3


@pytest.mark.asyncio
async def test_mark_mastered(db_session, test_student):
    data = WrongQuestionCreate(source_image_url="https://cdn.example.com/c.jpg")
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)
    updated = await mark_mastered(db_session, wq=wq, is_mastered=True)
    assert updated.is_mastered is True
    assert updated.mastered_at is not None
    un = await mark_mastered(db_session, wq=updated, is_mastered=False)
    assert un.is_mastered is False
    assert un.mastered_at is None


import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app


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
        mock_wx.return_value = {"openid": f"wq_api_test_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_wrong_question_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/test.jpg",
            "question_text": "She __ to school every day.",
            "student_answer": "go",
            "correct_answer": "goes",
            "question_type": "单选",
            "difficulty": 2,
            "tags": ["主谓一致"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["question_type"] == "单选"
    assert body["data"]["is_mastered"] is False
    assert body["data"]["id"] != ""


@pytest.mark.asyncio
async def test_create_wrong_question_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/test.jpg"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_wrong_questions_api(client: AsyncClient, auth_headers):
    for i in range(2):
        await client.post(
            "/api/v1/wrong-questions/",
            json={"source_image_url": f"https://cdn.example.com/{i}.jpg"},
            headers=auth_headers,
        )
    resp = await client.get("/api/v1/wrong-questions/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] >= 2
    assert isinstance(body["data"]["items"], list)


@pytest.mark.asyncio
async def test_get_wrong_question_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/get_test.jpg"},
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/wrong-questions/{wq_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == wq_id


@pytest.mark.asyncio
async def test_get_wrong_question_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(
        f"/api/v1/wrong-questions/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_mastered_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/mastered.jpg"},
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]
    resp = await client.patch(
        f"/api/v1/wrong-questions/{wq_id}/mastered",
        json={"is_mastered": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_mastered"] is True
    assert resp.json()["data"]["mastered_at"] is not None
