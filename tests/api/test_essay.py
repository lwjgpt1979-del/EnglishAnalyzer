"""作文精修 API 测试（D-109）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d2_payments import Membership


@pytest.fixture(autouse=True)
def _force_llm_dev_mock(monkeypatch):
    """强制 dev-mock，绝不真打付费 LLM。"""
    from app.services import essay_service
    monkeypatch.setattr(essay_service, "is_llm_dev_mode", lambda: True)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_pro(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"essayapi_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    async with _async_session_factory() as s:
        s.add(Membership(id=uuid.uuid4(), user_id=uuid.UUID(me["id"]), tier="pro",
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.commit()
    return headers


@pytest.mark.asyncio
async def test_essay_requires_auth(client):
    r = await client.post("/api/v1/essays", json={"original_text": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_essay_flow(client):
    headers = await _login_pro(client, uuid.uuid4().hex[:6])
    r = await client.post("/api/v1/essays",
                          json={"original_text": "I am very good.", "essay_type": "话题作文"},
                          headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["polished_text"] and len(data["scores"]) == 4 and data["status"] == "completed"
    eid = data["id"]
    lst = (await client.get("/api/v1/essays", headers=headers)).json()["data"]
    assert lst["total"] >= 1 and any(it["id"] == eid for it in lst["items"])
    detail = (await client.get(f"/api/v1/essays/{eid}", headers=headers)).json()["data"]
    assert detail["id"] == eid and len(detail["issues"]) >= 1
