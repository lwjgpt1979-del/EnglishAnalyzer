"""R5.3 通用词库管理 HTTP:创建词库 / 加词条(按词形自动建)/ 列条目 / 非超管 403。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User

_TAG = "vladm"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _make_admin(client, suffix):
    openid = f"{_TAG}_adm_{suffix}"
    h = await _login(client, openid)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == openid))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return h


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM vocab_list_item WHERE word_id IN "
                              "(SELECT id FROM vocabulary_words WHERE word LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM vocab_list WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_create_list_add_items(client):
    admin = await _make_admin(client, "a")
    try:
        r = await client.post("/api/v1/admin/vocab-lists",
                              json={"name": f"{_TAG}高考3500", "exam_level": "senior",
                                    "source_type": "official_syllabus", "status": "published"}, headers=admin)
        assert r.status_code == 200, r.text
        list_id = r.json()["data"]["id"]

        # 加词条(按词形自动建词)
        r = await client.post(f"/api/v1/admin/vocab-lists/{list_id}/items",
                              json={"items": [{"word": f"{_TAG}abandon", "rank": 1, "star": 5},
                                              {"word": f"{_TAG}ability", "rank": 2, "star": 4}]}, headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total"] == 2

        # 列条目(按 rank)
        r = await client.get(f"/api/v1/admin/vocab-lists/{list_id}/items", headers=admin)
        items = r.json()["data"]["items"]
        assert items[0]["word"] == f"{_TAG}abandon" and items[0]["star"] == 5

        # 词库列表可见
        r = await client.get("/api/v1/admin/vocab-lists", headers=admin)
        assert any(it["id"] == list_id for it in r.json()["data"]["items"])
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    stu = await _login(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/vocab-lists", headers=stu)
    assert r.status_code == 403
