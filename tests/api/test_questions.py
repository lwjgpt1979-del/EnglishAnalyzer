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
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp


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
    """返回 (node_id, single_choice_question_id)；新 session commit，跨请求可见。

    R8 KP-First:直插 5 道 platform 仿真题(type='sim',is_fallback)挂到知识 node(platform_question_kp),
    含一道 answer="B" 的单选,保证 test_submit_correct/wrong_attempt 的 == "B" 断言确定。
    """
    node_id = uuid.uuid4()
    single_b_id: uuid.UUID | None = None
    async with _async_session_factory() as s:
        s.add(KnowledgeNode(
            id=node_id, axis="knowledge", node_kind="句法", name="M3 测试 KP",
            code=f"m3-test-{uuid.uuid4().hex[:8]}", status="active", source="seed"))
        await s.flush()
        specs = [
            ("单选", ["A. x", "B. y", "C. z", "D. w"], "B"),
            ("单选", ["A. x", "B. y", "C. z", "D. w"], "A"),
            ("填空", None, "goes"),
            ("判断", None, "对"),
            ("填空", None, "can|may"),
        ]
        for qtype, opts, ans in specs:
            qid = uuid.uuid4()
            s.add(PlatformQuestion(
                id=qid, type="sim", is_fallback=True, status="published",
                question_type=qtype, stem=f"占位 {qtype} 题干",
                options=opts, answer=ans, explanation="占位解析", difficulty=1))
            await s.flush()
            s.add(PlatformQuestionKp(question_id=qid, node_id=node_id))
            if qtype == "单选" and ans == "B" and single_b_id is None:
                single_b_id = qid
        await s.commit()
        return node_id, single_b_id


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

    # 取该 node 全部 5 题的 (id, type, answer)，按真答案造 3 对 2 错
    async with _async_session_factory() as s:
        rows = (await s.execute(
            select(PlatformQuestion)
            .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
            .where(PlatformQuestionKp.node_id == kp_id).limit(5)
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


# R8 Phase6a-2 part3 已退役 test_kp_accuracy_endpoint / test_exam_history_endpoint:
# GET /kp-accuracy、/exam-history 端点已删(读冻结 sim 表,与诊断页 kp_dimension 重复/已空)。


# R8 KP-First 已退役 test_practice_questions_filter_by_dimension /
# test_practice_questions_no_dimension_returns_all:
# 「维度(dimension)过滤」在 KP-First 已弃用(questions.py 的 dimension 参数标注已弃用),
# 且 serve_by_node 现按 node 出题、不足时现生成补齐到 limit(不再是"返回固定几道"),
# 原「按维度筛/返回精确条数」的语义不复存在。节点化出题覆盖见上方 test_list_questions_*。
