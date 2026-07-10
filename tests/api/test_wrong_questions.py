from app.core.config import settings


def test_settings_has_deepseek_api_key():
    """settings 必须有 deepseek_api_key 字段（值可为 placeholder）。"""
    assert hasattr(settings, "deepseek_api_key")
    assert isinstance(settings.deepseek_api_key, str)


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
async def test_mark_mastered_api(client: AsyncClient):
    """KP-First 直切:/{id}/mastered 操作 wrong_record(id 为 wrong_record id)。"""
    import uuid as _uuid
    from unittest.mock import AsyncMock as _AM, patch as _patch
    from sqlalchemy import select as _select
    from app.core.database import _async_session_factory as _sf
    from app.models.d1_users import User as _User
    from app.models.d16_question_domain import WrongRecord as _WR

    openid = f"wqmast_{_uuid.uuid4().hex[:8]}"
    with _patch("app.services.auth_service.wechat_code2session", new_callable=_AM) as m:
        m.return_value = {"openid": openid}
        lr = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    headers = {"Authorization": f"Bearer {lr.json()['data']['access_token']}"}
    async with _sf() as s:
        uid = (await s.execute(_select(_User.id).where(_User.openid == openid))).scalar_one()
        wr_id = _uuid.uuid4()
        s.add(_WR(id=wr_id, student_id=uid, q_scope="uploaded", question_id=_uuid.uuid4(), status="open"))
        await s.commit()
    try:
        resp = await client.patch(
            f"/api/v1/wrong-questions/{wr_id}/mastered",
            json={"is_mastered": True}, headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_mastered"] is True
        assert resp.json()["data"]["mastered_at"] is not None
    finally:
        async with _sf() as s:
            await s.execute(_WR.__table__.delete().where(_WR.student_id == uid))
            await s.commit()


from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_analyze_wrong_question_service(db_session, test_student):
    """ai_service.analyze_wrong_question 应写入 AiAnalysis 并返回对象。"""
    from app.services.ai_service import analyze_wrong_question

    data = WrongQuestionCreate(
        source_image_url="https://cdn.example.com/svc_test.jpg",
        question_text="He don't like apples.",
        student_answer="don't",
        correct_answer="doesn't",
        question_type="单选",
    )
    wq = await create_wrong_question(db_session, student_id=test_student.id, data=data)

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"error_types": ["主谓一致错误"], "knowledge_points": ["第三人称单数助动词"], '
        '"diagnosis": "学生对第三人称单数助动词使用错误。", '
        '"suggestions": "复习主谓一致规则，重点记忆 does/doesn\'t。", '
        '"confidence_score": 0.95}'
    )
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 80

    with patch("app.services.ai_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.ai_service.chat_completion",
               new=AsyncMock(return_value=mock_response)):

        analysis = await analyze_wrong_question(
            db_session, wq=wq, student_id=test_student.id
        )

    assert analysis.llm_provider == "deepseek"
    assert analysis.error_types == ["主谓一致错误"]
    assert analysis.knowledge_points == ["第三人称单数助动词"]
    assert analysis.tokens_used == 280
    assert analysis.confidence_score == 0.95
    assert analysis.wrong_question_id == wq.id


@pytest.mark.asyncio
async def test_analyze_endpoint(client: AsyncClient, auth_headers):
    """POST /wrong-questions/{id}/analyze 应返回 AiAnalysisOut。"""
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/analyze_test.jpg",
            "question_text": "She don't like coffee.",
            "student_answer": "don't",
            "correct_answer": "doesn't",
            "question_type": "单选",
        },
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"error_types": ["主谓一致"], "knowledge_points": ["does/doesn\'t"], '
        '"diagnosis": "主谓不一致错误。", "suggestions": "复习第三人称单数。", '
        '"confidence_score": 0.9}'
    )
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 60

    with patch("app.services.ai_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.ai_service.chat_completion",
               new=AsyncMock(return_value=mock_response)):

        resp = await client.post(
            f"/api/v1/wrong-questions/{wq_id}/analyze", headers=auth_headers
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["llm_provider"] == "deepseek"
    assert body["data"]["error_types"] == ["主谓一致"]
    assert body["data"]["tokens_used"] == 210
    assert body["data"]["wrong_question_id"] == wq_id


@pytest.mark.asyncio
async def test_analyze_not_found(client: AsyncClient, auth_headers):
    """不存在的 wq_id → 404。"""
    resp = await client.post(
        f"/api/v1/wrong-questions/{uuid.uuid4()}/analyze", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_analyses_endpoint(client: AsyncClient, auth_headers):
    """GET /wrong-questions/{id}/analyses 返回分析列表。"""
    create_resp = await client.post(
        "/api/v1/wrong-questions/",
        json={
            "source_image_url": "https://cdn.example.com/analyses_test.jpg",
            "question_text": "I has a dog.",
            "student_answer": "has",
            "correct_answer": "have",
        },
        headers=auth_headers,
    )
    wq_id = create_resp.json()["data"]["id"]

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"error_types": ["助动词错误"], "knowledge_points": ["have/has"], '
        '"diagnosis": "主谓一致错误。", "suggestions": "复习助动词。", '
        '"confidence_score": 0.88}'
    )
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50

    with patch("app.services.ai_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.ai_service.chat_completion",
               new=AsyncMock(return_value=mock_response)):
        for _ in range(2):
            await client.post(
                f"/api/v1/wrong-questions/{wq_id}/analyze", headers=auth_headers
            )

    resp = await client.get(
        f"/api/v1/wrong-questions/{wq_id}/analyses", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert len(body["data"]) == 2


# ─── M3 关联视图：按知识点查错题（D-093）──────────────────────────────────────

import pytest_asyncio as _pytest_asyncio_m3  # noqa: F401 (确保已导入)


# R8 Phase6b:按 KP 查错题的 service(list_wrong_questions_by_kp,join wrong_question_knowledge_points)
# 及其 _make_kp/_link_wq_kp 种子已退役——错题按知识点查已改走节点化 wrong_center_service.list_by_node
# (见下方 API 测试,直读 wrong_record)。对应两个 service 单测一并移除。


@pytest.mark.asyncio
async def test_list_wrong_questions_by_kp_api(client: AsyncClient, auth_headers):
    """空关联返回 0；接口可用。"""
    random_kp_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/wrong-questions/by-kp/{random_kp_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []


@pytest.mark.asyncio
async def test_list_wrong_questions_source_filter(db_session, test_student):
    # 上传来源
    await create_wrong_question(db_session, student_id=test_student.id, data=WrongQuestionCreate(
        source_image_url="https://cdn.example.com/up.jpg", question_text="upload q"))
    # 作业来源
    from app.models.d3_wrong_questions import WrongQuestion
    db_session.add(WrongQuestion(
        id=uuid.uuid4(), student_id=test_student.id,
        source_image_url="assignment://abc", question_text="assign q"))
    await db_session.flush()
    from app.services import wrong_question_service
    _, total_all = await wrong_question_service.list_wrong_questions(db_session, student_id=test_student.id)
    items_a, total_a = await wrong_question_service.list_wrong_questions(
        db_session, student_id=test_student.id, source="assignment")
    items_u, total_u = await wrong_question_service.list_wrong_questions(
        db_session, student_id=test_student.id, source="upload")
    assert total_all == 2
    assert total_a == 1 and items_a[0].source_image_url.startswith("assignment://")
    assert total_u == 1 and not items_u[0].source_image_url.startswith("assignment://")
