"""R2.5 平台题管理 HTTP:预生成仿真 / 列表过滤 / 审核 / 非超管 403。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services.kp_normalize import normalize_kp_name

_TAG = "pqhttp"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _make_admin(client, suffix):
    openid = f"{_TAG}_adm_{suffix}"
    h = await _login_as(client, openid)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == openid))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return h


async def _seed_real():
    node_id, real_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}KP",
                             code=f"{_TAG}-n", status="active", source="textbook"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias=f"{_TAG}KP",
                         alias_norm=normalize_kp_name(f"{_TAG}KP"), source="seed"))
        db.add(PlatformQuestion(id=real_id, type="real", question_type="单选",
                                stem=f"{_TAG} 真题母题", answer="A", difficulty=3, status="published"))
        await db.flush()
        db.add(PlatformQuestionKp(question_id=real_id, node_id=node_id))
        await db.commit()
    return node_id, real_id


async def _cleanup():
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM platform_question_kp WHERE question_id IN "
                              "(SELECT id FROM platform_question WHERE stem LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_gen_sim_list_review(client):
    node_id, real_id = await _seed_real()
    try:
        admin = await _make_admin(client, "a")
        # 预生成 2 道仿真
        r = await client.post(f"/api/v1/admin/platform-questions/{real_id}/gen-sim?count=2", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["generated"] == 2
        sim_ids = r.json()["data"]["sim_ids"]

        # 列表过滤 type=sim,挂该 node
        r = await client.get(f"/api/v1/admin/platform-questions?type=sim&node_id={node_id}", headers=admin)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) >= 2 and all(it["type"] == "sim" and it["parent_real_id"] == str(real_id) for it in items)

        # 审核通过其一 → published
        r = await client.post(f"/api/v1/admin/platform-questions/{sim_ids[0]}/review",
                              json={"approve": True}, headers=admin)
        assert r.status_code == 200 and r.json()["data"]["status"] == "published"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    node_id, real_id = await _seed_real()
    try:
        stu = await _login_as(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
        r = await client.post(f"/api/v1/admin/platform-questions/{real_id}/gen-sim", headers=stu)
        assert r.status_code == 403
    finally:
        await _cleanup()
