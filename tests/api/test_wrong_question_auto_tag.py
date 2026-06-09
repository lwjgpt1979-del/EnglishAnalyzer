"""TDD: 错题自动打标 API（V2 M38）。

测试覆盖：
  1. POST /auto-tag 需要认证
  2. 无错题时 auto-tag 返回 200，processed=0
  3. 有 AI 分析的错题调用 auto-tag 后，tags 被填充
  4. GET /wrong-questions/?tag=xxx 按标签筛选返回正确结果
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_auto_tag_requires_auth(client):
    resp = await client.post("/api/v1/wrong-questions/auto-tag")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auto_tag_empty_student_returns_zero(client):
    token = await _login(client, f"autotag_{uuid.uuid4().hex[:8]}")
    resp = await client.post(
        "/api/v1/wrong-questions/auto-tag",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "processed" in data
    assert data["processed"] == 0


@pytest.mark.asyncio
async def test_analyze_auto_populates_tags(client):
    """上传错题 → AI 分析 → 分析完成后 tags 自动被填充（M38 内联打标）。"""
    token = await _login(client, f"autotag2_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 创建错题
    r = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/test.jpg"},
        headers=headers,
    )
    assert r.status_code == 200
    wq_id = r.json()["data"]["id"]
    # 刚创建时 tags 为空
    assert r.json()["data"]["tags"] is None

    # 2. 触发 AI 分析（dev mock），分析完成后自动打标
    r2 = await client.post(f"/api/v1/wrong-questions/{wq_id}/analyze", headers=headers)
    assert r2.status_code == 200

    # 3. 查询错题，tags 应已被自动填充（来自 AI knowledge_points）
    r3 = await client.get(f"/api/v1/wrong-questions/{wq_id}", headers=headers)
    tags = r3.json()["data"]["tags"]
    assert tags is not None, "analyze 后 tags 应自动填充"
    assert len(tags) > 0


@pytest.mark.asyncio
async def test_list_wrong_questions_filter_by_tag(client):
    """GET /wrong-questions/?tag=xxx 只返回含该 tag 的错题。"""
    token = await _login(client, f"autotag3_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    # 创建错题 → AI 分析（inline 自动打标）
    r = await client.post(
        "/api/v1/wrong-questions/",
        json={"source_image_url": "https://cdn.example.com/t2.jpg"},
        headers=headers,
    )
    wq_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/wrong-questions/{wq_id}/analyze", headers=headers)

    # 拿到实际 tag
    r_wq = await client.get(f"/api/v1/wrong-questions/{wq_id}", headers=headers)
    first_tag = r_wq.json()["data"]["tags"][0]

    # 按 tag 筛选（使用 params= 确保中文/空格正确 URL 编码）
    r_list = await client.get(
        "/api/v1/wrong-questions/",
        params={"tag": first_tag},
        headers=headers,
    )
    assert r_list.status_code == 200
    items = r_list.json()["data"]["items"]
    assert len(items) >= 1
    # 所有返回错题都含该 tag
    for item in items:
        assert first_tag in (item.get("tags") or [])
