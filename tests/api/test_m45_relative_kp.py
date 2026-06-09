"""M45 — 家长端查看孩子 KP 台账"""
from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


async def _make_relative_pair(client: AsyncClient):
    """student + relative 绑定，返回 (stu_token, rel_token, student_id)"""
    stu_token = await _login(client, f"stu_m45_{uuid.uuid4().hex[:6]}")
    rel_token = await _login(client, f"rel_m45_{uuid.uuid4().hex[:6]}")

    r = await client.post("/api/v1/relative/invite-code",
                          headers={"Authorization": f"Bearer {stu_token}"})
    code = r.json()["data"]["code"]

    await client.post("/api/v1/relative/bind",
                      json={"code": code, "relationship": "parent"},
                      headers={"Authorization": f"Bearer {rel_token}"})

    r = await client.get("/api/v1/users/me",
                         headers={"Authorization": f"Bearer {stu_token}"})
    student_id = r.json()["data"]["id"]
    return stu_token, rel_token, student_id


@pytest.mark.asyncio
async def test_relative_can_view_child_kp_mastery(client: AsyncClient):
    """家长可以查看已绑定孩子的 KP 台账（空列表也正常返回）"""
    _, rel_token, student_id = await _make_relative_pair(client)
    r = await client.get(
        f"/api/v1/relative/students/{student_id}/kp-mastery",
        headers={"Authorization": f"Bearer {rel_token}"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_relative_unbound_student_is_403(client: AsyncClient):
    """未绑定的学生 → 403"""
    rel_token = await _login(client, f"rel2_m45_{uuid.uuid4().hex[:6]}")
    stranger_token = await _login(client, f"str_m45_{uuid.uuid4().hex[:6]}")

    r = await client.get("/api/v1/users/me",
                         headers={"Authorization": f"Bearer {stranger_token}"})
    stranger_id = r.json()["data"]["id"]

    r = await client.get(
        f"/api/v1/relative/students/{stranger_id}/kp-mastery",
        headers={"Authorization": f"Bearer {rel_token}"},
    )
    assert r.status_code == 403
