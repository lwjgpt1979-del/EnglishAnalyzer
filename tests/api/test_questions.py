"""V2 questions API 集成测试（D-079 / M3a）。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.main import app
from app.models.d4_knowledge import KnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.services import question_ai_service, question_service


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"m3_q_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_kp_with_questions() -> tuple[uuid.UUID, uuid.UUID]:
    """返回 (kp_id, single_choice_question_id)；新 session commit，跨请求可见。"""
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(),
            code=f"m3-test-{uuid.uuid4().hex[:8]}",
            name="M3 测试 KP",
            category="grammar",
            description="m3 test",
            applicable_grades=["小学5年级"],
            applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        qs = await question_ai_service.generate_questions(
            kp_name=kp.name, kp_category="grammar", kp_description="d", count=5,
        )
        await question_service.persist_questions(s, kp_id=kp.id, questions=qs)
        await s.commit()

        first_single = (await s.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp.id,
                SimulatedQuestion.question_type == "单选",
            ).limit(1)
        )).scalar_one()
        return kp.id, first_single.id


@pytest.mark.asyncio
async def test_list_questions_returns_no_answers(client):
    """前端拿到的题目不能含 answer 字段（防作弊）。"""
    kp_id, _ = await _seed_kp_with_questions()
    h = await _login(client, f"l_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        f"/api/v1/questions/kp/{kp_id}/practice-questions?limit=5",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) >= 5
    for q in items:
        assert "answer" not in q
        assert q["stem"]
        assert q["question_type"] in ["单选", "填空", "判断"]


@pytest.mark.asyncio
async def test_submit_correct_attempt(client):
    """单选题答对（dev mock 答案是 B）：correct=true，无 wrong_question_id。"""
    _, q_id = await _seed_kp_with_questions()
    h = await _login(client, f"c_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/questions/practice-attempts",
        json={"question_id": str(q_id), "user_answer": "B"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["correct"] is True
    assert body["wrong_question_id"] is None
    assert body["correct_answer"] == "B"
    assert body["explanation"]


@pytest.mark.asyncio
async def test_submit_wrong_attempt_creates_wrong_q(client):
    """单选题答错：correct=false，返回 wrong_question_id。"""
    _, q_id = await _seed_kp_with_questions()
    h = await _login(client, f"w_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/questions/practice-attempts",
        json={"question_id": str(q_id), "user_answer": "D"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["correct"] is False
    assert body["wrong_question_id"] is not None
    assert body["correct_answer"] == "B"


@pytest.mark.asyncio
async def test_submit_exam_attempts_batch(client):
    """模拟考批量：5 题提交 3 对 2 错 → total=5, correct_count=3。"""
    kp_id, _ = await _seed_kp_with_questions()

    # 取该 KP 全部 5 题的 (id, type, answer)，按真答案造 3 对 2 错
    async with _async_session_factory() as s:
        rows = (await s.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp_id
            ).limit(5)
        )).scalars().all()

    assert len(rows) == 5
    items = []
    for i, q in enumerate(rows):
        if i < 3:
            # 答对：填空答案可能形如 "can|may"，取第一个合法答案
            ua = q.answer.split("|")[0].strip()
        else:
            # 答错：拼一个绝不等于真答案的串
            ua = f"__wrong__{q.answer}"
        items.append({"question_id": str(q.id), "user_answer": ua})

    h = await _login(client, f"e_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/questions/exam-attempts",
        json={"items": items},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 5
    assert data["correct_count"] == 3
    assert len(data["items"]) == 5
    # 后 2 题应落错题
    wrong_items = [it for it in data["items"] if not it["correct"]]
    assert len(wrong_items) == 2
    for it in wrong_items:
        assert it["wrong_question_id"] is not None
