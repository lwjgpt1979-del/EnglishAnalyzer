"""R6.3 资源管理 HTTP:超管增/审核/编辑 + 学生只读 published + 非超管 403。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode

_TAG = "nrapi"


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


async def _seed_node() -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.commit()
    return nid


async def _cleanup(node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM node_resource WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_admin_crud_and_student_read(client):
    node_id = await _seed_node()
    try:
        admin = await _make_admin(client, "a")
        # 加 lecture(grammar)草稿
        r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
            "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
            "content_md": "语法讲解", "status": "draft"})
        assert r.status_code == 200, r.text
        lec_id = r.json()["data"]["id"]
        # 加 video 草稿
        r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
            "node_id": str(node_id), "resource_type": "video", "title": "视频", "media_url": "https://x/v.mp4"})
        video_id = r.json()["data"]["id"]

        # 审核队列(draft)含两条
        r = await client.get(f"/api/v1/admin/node-resources?node_id={node_id}&status=draft", headers=admin)
        assert r.json()["data"]["total"] == 2

        # 学生读:此时无 published → 空
        stu = await _login(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
        r = await client.get(f"/api/v1/curriculum/nodes/{node_id}/resources", headers=stu)
        assert r.status_code == 200 and r.json()["data"]["total"] == 0

        # 审核发布 video
        r = await client.post(f"/api/v1/admin/node-resources/{video_id}/review",
                              headers=admin, json={"approve": True})
        assert r.json()["data"]["status"] == "published"

        # 学生读:只见 video(lecture 仍 draft)
        r = await client.get(f"/api/v1/curriculum/nodes/{node_id}/resources", headers=stu)
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["id"] == video_id

        # 非超管不能加资源
        r = await client.post("/api/v1/admin/node-resources", headers=stu, json={
            "node_id": str(node_id), "resource_type": "video", "title": "x"})
        assert r.status_code == 403
    finally:
        await _cleanup(node_id)
