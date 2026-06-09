"""M46 — KP 趋势图（日快照 + trend API）"""
from __future__ import annotations
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_trend_empty_before_any_practice(client: AsyncClient):
    """未做过任何练习时 trend 返回空列表"""
    token = await _login(client, f"m46_{uuid.uuid4().hex[:6]}")
    r = await client.get(
        "/api/v1/kp-mastery/trend?kp_key=present_simple",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.asyncio
async def test_trend_has_point_after_practice(client: AsyncClient):
    """完成一次练习后 trend 至少有一条今天的快照"""
    token = await _login(client, f"m46_{uuid.uuid4().hex[:6]}")

    # 提交一次答题（利用 kp_mastery_service 直接写入）
    r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    student_id = r.json()["data"]["id"]

    # 通过练习生成+提交触发 upsert_mastery
    # 先生成一道练习题
    gen_r = await client.post(
        "/api/v1/practice/generate",
        json={"knowledge_point": "present_simple", "count": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gen_r.status_code == 200
    question = gen_r.json()["data"][0]

    # 提交答案（无论对错都会写快照）
    await client.post(
        "/api/v1/practice/submit",
        json={"question_id": question["id"], "answer": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 查趋势
    r = await client.get(
        "/api/v1/kp-mastery/trend?kp_key=present_simple",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    points = r.json()["data"]
    assert len(points) >= 1

    today = str(date.today())
    assert any(p["date"] == today for p in points)
    assert all(0.0 <= p["accuracy"] <= 1.0 for p in points)


@pytest.mark.asyncio
async def test_trend_dedup_same_day(client: AsyncClient):
    """同一天多次答题只产生一条快照（daily 去重）"""
    token = await _login(client, f"m46_{uuid.uuid4().hex[:6]}")

    for _ in range(3):
        gen_r = await client.post(
            "/api/v1/practice/generate",
            json={"knowledge_point": "present_simple", "count": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        question = gen_r.json()["data"][0]
        await client.post(
            "/api/v1/practice/submit",
            json={"question_id": question["id"], "answer": "A"},
            headers={"Authorization": f"Bearer {token}"},
        )

    r = await client.get(
        "/api/v1/kp-mastery/trend?kp_key=present_simple&days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    points = r.json()["data"]
    today = str(date.today())
    today_points = [p for p in points if p["date"] == today]
    assert len(today_points) == 1   # 去重，只有一条


@pytest.mark.asyncio
async def test_trend_snapshot_accuracy_reflects_cumulative(client: AsyncClient):
    """快照中的 accuracy 反映累积 correct/total，而非单次"""
    token = await _login(client, f"m46_{uuid.uuid4().hex[:6]}")

    # 提交 2 次（dev mock 答案是固定的 A，多次提交结果可能相同）
    for _ in range(2):
        gen_r = await client.post(
            "/api/v1/practice/generate",
            json={"knowledge_point": "present_simple", "count": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        q = gen_r.json()["data"][0]
        await client.post(
            "/api/v1/practice/submit",
            json={"question_id": q["id"], "answer": q.get("answer", "A")},
            headers={"Authorization": f"Bearer {token}"},
        )

    r = await client.get(
        "/api/v1/kp-mastery/trend?kp_key=present_simple",
        headers={"Authorization": f"Bearer {token}"},
    )
    points = r.json()["data"]
    assert len(points) >= 1
    p = points[-1]
    total = p["correct_count"] + p["wrong_count"]
    assert total >= 2                         # 累积计数
    if total > 0:
        expected = p["correct_count"] / total
        assert abs(p["accuracy"] - expected) < 0.001
