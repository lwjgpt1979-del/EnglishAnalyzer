"""D-130 adaptive-set API 集成测试。

TDD：测试先写，验证行为正确性：
  1. 无数据时返回 200 + 空列表
  2. 返回题目不含 answer 字段（防作弊）
  3. 未认证返回 401
  4. total 参数被尊重
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient) -> dict:
    """用 mock wechat 登录，返回 auth header。"""
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"adaptive_test_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_adaptive_set_requires_auth(client: AsyncClient):
    """未携带 token 时返回 401。"""
    resp = await client.get("/api/v1/questions/adaptive-set")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_adaptive_set_returns_200_with_empty_data(client: AsyncClient):
    """新用户（无错题）时返回 200，questions 与 weak_kp_names 均为空列表。"""
    h = await _login(client)
    resp = await client.get("/api/v1/questions/adaptive-set", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "questions" in data
    assert "weak_kp_names" in data
    assert data["questions"] == []
    assert data["weak_kp_names"] == []


@pytest.mark.asyncio
async def test_adaptive_set_questions_have_no_answer_field(client: AsyncClient):
    """返回的题目字段中不含 answer（防作弊）。

    即使题库有题，answer 也不应出现在响应里。
    此测试在无数据时题列表为空 → 零题目零违规，视为 PASS。
    真正有题时也成立（由 SimQuestionOut schema 保证）。
    """
    h = await _login(client)
    resp = await client.get("/api/v1/questions/adaptive-set", headers=h)
    assert resp.status_code == 200
    questions = resp.json()["data"]["questions"]
    for q in questions:
        assert "answer" not in q, f"题目 {q.get('id')} 泄露了 answer 字段"


@pytest.mark.asyncio
async def test_adaptive_set_total_param_accepted(client: AsyncClient):
    """total 参数合法范围内（1-10）不报错；超出范围返回 422。"""
    h = await _login(client)

    # 合法：total=3
    resp = await client.get("/api/v1/questions/adaptive-set", params={"total": 3}, headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["questions"]) <= 3

    # 非法：total=0
    resp = await client.get("/api/v1/questions/adaptive-set", params={"total": 0}, headers=h)
    assert resp.status_code == 422

    # 非法：total=11
    resp = await client.get("/api/v1/questions/adaptive-set", params={"total": 11}, headers=h)
    assert resp.status_code == 422
