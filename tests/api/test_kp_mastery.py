"""TDD: 个人知识点掌握台账 API（M39）。

测试覆盖：
  1. GET /kp-mastery/ 需要认证
  2. 新学生查询返回空列表
  3. 自适应练习答题后，掌握台账自动更新
  4. 多次答题累加 correct_count / wrong_count
  5. 返回列表按正确率升序（弱项在前）
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


async def _generate_and_submit(client, headers: dict, *, kp: str, correct: bool) -> None:
    """生成一道练习题并提交答案（correct=True 提交正确答案，False 提交错误答案）。"""
    r = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": kp, "count": 1, "difficulty": 3},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    q = r.json()["data"][0]
    qid = q["id"]

    # dev mock 答案固定为 "goes"（见 practice_service._dev_mock_questions）
    answer = "goes" if correct else "wrong_answer_xyz"
    await client.post(
        "/api/v1/practice/submit",
        json={"question_id": qid, "answer": answer, "time_spent_sec": 5},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_kp_mastery_requires_auth(client):
    resp = await client.get("/api/v1/kp-mastery/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_kp_mastery_empty_for_new_student(client):
    token = await _login(client, f"kpm_{uuid.uuid4().hex[:8]}")
    resp = await client.get(
        "/api/v1/kp-mastery/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_practice_submit_updates_mastery(client):
    """答题后掌握台账应自动写入一条记录。"""
    token = await _login(client, f"kpm_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    await _generate_and_submit(client, headers, kp="一般现在时", correct=True)

    resp = await client.get("/api/v1/kp-mastery/", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["kp_key"] == "一般现在时"
    assert item["correct_count"] == 1
    assert item["wrong_count"] == 0


@pytest.mark.asyncio
async def test_mastery_accumulates_across_answers(client):
    """连续答题，correct_count 和 wrong_count 累加而非覆盖。"""
    token = await _login(client, f"kpm_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    kp = "过去进行时"
    await _generate_and_submit(client, headers, kp=kp, correct=True)
    await _generate_and_submit(client, headers, kp=kp, correct=True)
    await _generate_and_submit(client, headers, kp=kp, correct=False)

    resp = await client.get("/api/v1/kp-mastery/", headers=headers)
    items = resp.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["correct_count"] == 2
    assert item["wrong_count"] == 1


@pytest.mark.asyncio
async def test_mastery_sorted_by_accuracy_asc(client):
    """弱项（正确率低）排在前面。"""
    token = await _login(client, f"kpm_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    # KP-A: 1对0错 → 100%
    await _generate_and_submit(client, headers, kp="KP-A强", correct=True)
    # KP-B: 0对1错 → 0%
    await _generate_and_submit(client, headers, kp="KP-B弱", correct=False)

    resp = await client.get("/api/v1/kp-mastery/", headers=headers)
    items = resp.json()["data"]
    assert len(items) == 2
    # 弱项在前
    assert items[0]["kp_key"] == "KP-B弱"
    assert items[1]["kp_key"] == "KP-A强"
