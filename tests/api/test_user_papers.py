"""整卷上传 API 测试（D-089 / M4）。httpx ASGITransport 会 inline await 后台任务，
故 POST 返回时 OCR 管线已跑完，可直接断言 completed + 2 题。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": f"m4_paper_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_create_paper_runs_pipeline(client):
    headers = await _login(client, "create")
    resp = await client.post(
        "/api/v1/user-papers",
        headers=headers,
        json={"source_image_urls": ["https://mock/p1.jpg"], "title": "期中卷"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    paper_id = data["id"]
    assert data["title"] == "期中卷"

    detail = await client.get(f"/api/v1/user-papers/{paper_id}", headers=headers)
    assert detail.status_code == 200
    d = detail.json()["data"]
    assert d["ocr_status"] == "completed"
    assert d["question_count"] == 2
    assert len(d["questions"]) == 2


@pytest.mark.asyncio
async def test_list_papers(client):
    headers = await _login(client, "list")
    await client.post(
        "/api/v1/user-papers",
        headers=headers,
        json={"source_image_urls": ["https://mock/p1.jpg"]},
    )
    resp = await client.get("/api/v1/user-papers", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] >= 1
    assert any(it["question_count"] == 2 for it in body["items"])


@pytest.mark.asyncio
async def test_get_paper_not_found(client):
    headers = await _login(client, "notfound")
    resp = await client.get(f"/api/v1/user-papers/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
