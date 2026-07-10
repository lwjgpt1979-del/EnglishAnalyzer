"""AI 练习模块测试。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.main import app
from app.schemas.practice import (
    GenerateQuestionsRequest,
    PracticeQuestionOut,
    PracticeRecordOut,
    PracticeStatsOut,
    SubmitAnswerRequest,
    SubmitAnswerResult,
)


# ── Schema 单元测试 ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时 API 集成测试打到真实 API
    导致 mock 答案断言（answer=='goes'）不稳定。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


def test_generate_request_defaults():
    req = GenerateQuestionsRequest()
    assert req.knowledge_point is None
    assert req.count == 5
    assert req.difficulty == 3


def test_generate_request_clamps_count_via_validation():
    req = GenerateQuestionsRequest(knowledge_point="一般现在时", count=3, difficulty=2)
    assert req.count == 3
    assert req.knowledge_point == "一般现在时"


def test_practice_question_out_has_no_answer_field():
    out = PracticeQuestionOut(
        id=uuid.uuid4(),
        knowledge_point_id=uuid.uuid4(),
        knowledge_point_name="一般现在时",
        question_type="单选",
        difficulty=2,
        stem="She ___ to school every day.",
        options=["go", "goes", "going", "went"],
    )
    dumped = out.model_dump()
    assert "answer" not in dumped
    assert "explanation" not in dumped
    assert dumped["options"] == ["go", "goes", "going", "went"]


def test_submit_answer_request_schema():
    req = SubmitAnswerRequest(question_id=uuid.uuid4(), answer="goes", time_spent_sec=12)
    assert req.answer == "goes"
    assert req.time_spent_sec == 12


def test_submit_answer_result_schema():
    res = SubmitAnswerResult(
        record_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        is_correct=True,
        correct_answer="goes",
        explanation="主语第三人称单数。",
    )
    assert res.is_correct is True
    assert res.correct_answer == "goes"


def test_practice_stats_out_schema():
    out = PracticeStatsOut(
        total_practiced=10,
        total_correct=7,
        correct_rate=0.7,
        by_knowledge_point={"一般现在时": {"practiced": 5, "correct": 3}},
    )
    assert out.correct_rate == 0.7
    assert out.by_knowledge_point["一般现在时"]["correct"] == 3


# ── Service 集成测试（需要真实 DB）─────────────────────────────────────────────

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services.auth_service import upsert_user
from app.services.practice_service import (
    generate_practice_questions,
    get_practice_history,
    get_practice_stats,
    get_question,
    submit_answer,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student_user(db_session):
    user = await upsert_user(db_session, openid=f"practice_svc_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


_MOCK_QUESTIONS_JSON = (
    '[{"stem": "She ___ to school.", "options": ["go", "goes", "going", "gone"], '
    '"answer": "goes", "explanation": "第三人称单数。"}, '
    '{"stem": "They ___ happy.", "options": ["is", "am", "are", "be"], '
    '"answer": "are", "explanation": "复数主语用 are。"}, '
    '{"stem": "I ___ a student.", "options": ["is", "am", "are", "be"], '
    '"answer": "am", "explanation": "第一人称单数用 am。"}]'
)


def _make_mock_response(json_text: str):
    from unittest.mock import MagicMock
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = json_text
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 200
    return resp


# R8 Phase6-前置:get_or_create_knowledge_point 已退役(练习不再建 knowledge_points,
# 知识点改经 match_kp 挂 node),对应两个单测一并移除。


@pytest.mark.asyncio
async def test_generate_practice_questions(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.practice_service.chat_completion",
               new=AsyncMock(return_value=_make_mock_response(_MOCK_QUESTIONS_JSON))):
        questions = await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point="一般现在时",
            count=3,
            difficulty=2,
        )
    await db_session.flush()
    assert len(questions) == 3
    assert questions[0].content["stem"] == "She ___ to school."
    assert questions[0].content["answer"] == "goes"
    assert questions[0].question_type == "单选"
    assert questions[0].difficulty == 2


@pytest.mark.asyncio
async def test_generate_uses_dev_mock_when_placeholder_key(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point="主谓一致",
            count=2,
            difficulty=3,
        )
    await db_session.flush()
    assert len(questions) == 2
    for q in questions:
        assert "stem" in q.content
        assert "answer" in q.content
        assert "options" in q.content


@pytest.mark.asyncio
async def test_generate_no_knowledge_point_no_diagnosis_raises(db_session, student_user):
    with pytest.raises(AppError) as exc_info:
        await generate_practice_questions(
            db_session,
            student_id=student_user.id,
            knowledge_point=None,
            count=3,
            difficulty=3,
        )
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_get_question(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="时态", count=1, difficulty=2,
        )
    await db_session.flush()
    q = await get_question(db_session, question_id=questions[0].id)
    assert q is not None
    assert q.id == questions[0].id


@pytest.mark.asyncio
async def test_submit_answer_correct(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.practice_service.chat_completion",
               new=AsyncMock(return_value=_make_mock_response(_MOCK_QUESTIONS_JSON))):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="一般现在时", count=3, difficulty=2,
        )
    await db_session.flush()
    record = await submit_answer(
        db_session,
        student_id=student_user.id,
        question_id=questions[0].id,
        answer="goes",
        time_spent_sec=10,
    )
    await db_session.flush()
    assert record.is_correct is True
    assert record.student_id == student_user.id
    assert record.trigger_type == "module8_free"


@pytest.mark.asyncio
async def test_submit_answer_wrong(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=False), \
         patch("app.services.practice_service.chat_completion",
               new=AsyncMock(return_value=_make_mock_response(_MOCK_QUESTIONS_JSON))):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="一般现在时", count=3, difficulty=2,
        )
    await db_session.flush()
    record = await submit_answer(
        db_session, student_id=student_user.id,
        question_id=questions[0].id, answer="go",
    )
    await db_session.flush()
    assert record.is_correct is False


@pytest.mark.asyncio
async def test_submit_answer_question_not_found_raises(db_session, student_user):
    with pytest.raises(AppError) as exc_info:
        await submit_answer(
            db_session, student_id=student_user.id,
            question_id=uuid.uuid4(), answer="x",
        )
    assert exc_info.value.code == 404


@pytest.mark.asyncio
async def test_get_practice_history(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="时态", count=2, difficulty=2,
        )
    await db_session.flush()
    for q in questions:
        await submit_answer(
            db_session, student_id=student_user.id,
            question_id=q.id, answer=q.content["answer"],
        )
    await db_session.flush()
    items, total = await get_practice_history(
        db_session, student_id=student_user.id, skip=0, limit=10
    )
    assert total >= 2
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_get_practice_stats(db_session, student_user):
    with patch("app.services.practice_service.is_llm_dev_mode", return_value=True):
        questions = await generate_practice_questions(
            db_session, student_id=student_user.id,
            knowledge_point="主谓一致", count=2, difficulty=2,
        )
    await db_session.flush()
    await submit_answer(db_session, student_id=student_user.id,
                        question_id=questions[0].id, answer=questions[0].content["answer"])
    await submit_answer(db_session, student_id=student_user.id,
                        question_id=questions[1].id, answer="__definitely_wrong__")
    await db_session.flush()
    stats = await get_practice_stats(db_session, student_id=student_user.id)
    assert stats["total_practiced"] >= 2
    assert stats["total_correct"] >= 1
    assert 0.0 <= stats["correct_rate"] <= 1.0


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
        mock_wx.return_value = {"openid": f"practice_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_generate_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 3, "difficulty": 2},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_questions_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 3, "difficulty": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    questions = body["data"]
    assert len(questions) == 3
    assert "answer" not in questions[0]
    assert "explanation" not in questions[0]
    assert "options" in questions[0]
    assert questions[0]["knowledge_point_name"] == "一般现在时"


@pytest.mark.asyncio
async def test_submit_answer_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "一般现在时", "count": 1, "difficulty": 2},
        headers=auth_headers,
    )
    q = gen_resp.json()["data"][0]
    submit_resp = await client.post(
        "/api/v1/practice/submit",
        json={"question_id": q["id"], "answer": "goes", "time_spent_sec": 8},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 200, submit_resp.text
    data = submit_resp.json()["data"]
    assert data["is_correct"] is True
    assert data["correct_answer"] == "goes"
    assert "explanation" in data


@pytest.mark.asyncio
async def test_submit_answer_not_found_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/practice/submit",
        json={"question_id": str(uuid.uuid4()), "answer": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_practice_history_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "时态", "count": 2, "difficulty": 2},
        headers=auth_headers,
    )
    for q in gen_resp.json()["data"]:
        await client.post(
            "/api/v1/practice/submit",
            json={"question_id": q["id"], "answer": "goes"},
            headers=auth_headers,
        )
    resp = await client.get("/api/v1/practice/history", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] >= 2
    assert isinstance(body["data"]["items"], list)


@pytest.mark.asyncio
async def test_practice_stats_api(client: AsyncClient, auth_headers):
    gen_resp = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "主谓一致", "count": 2, "difficulty": 2},
        headers=auth_headers,
    )
    questions = gen_resp.json()["data"]
    await client.post(
        "/api/v1/practice/submit",
        json={"question_id": questions[0]["id"], "answer": "goes"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/practice/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_practiced" in data
    assert "correct_rate" in data
    assert "by_knowledge_point" in data
