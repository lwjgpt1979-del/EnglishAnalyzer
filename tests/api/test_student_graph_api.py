"""R4.3 个人图谱 HTTP:显式纳入 /enroll + 知识地图 /graph + 鉴权。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d17_curriculum_kg import UnitNode

_TAG = "sgapi"
VER, GRADE, SEM = f"{_TAG}版", "初中7年级", "上"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    token = r.json()["data"]["access_token"]
    async with _async_session_factory() as s:
        uid = (await s.execute(select(User.id).where(User.openid == openid))).scalar_one()
    return {"Authorization": f"Bearer {token}"}, uid


async def _seed_textbook_and_pref(uid):
    unit_id, n1, n2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=VER, grade=GRADE,
                              semester=SEM, unit_no=1, unit_title=f"{_TAG}U1"))
        for i, nid in enumerate((n1, n2)):
            db.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name=f"{_TAG}KP{i}",
                                 code=f"{_TAG}-{i}", status="active", source="seed"))
        await db.flush()
        db.add(UnitNode(unit_id=unit_id, node_id=n1, source="ai_extract"))
        db.add(UnitNode(unit_id=unit_id, node_id=n2, source="ai_extract"))
        await db.execute(update(User).where(User.id == uid).values(
            preferred_textbook_version=VER, preferred_grade=GRADE, preferred_semester=SEM))
        await db.commit()
    return n1, n2


async def _cleanup(uid, *nodes):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM unit_node WHERE node_id = ANY(:ns)"),
                         {"ns": [str(n) for n in nodes]})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": VER})
        await db.commit()


@pytest.mark.asyncio
async def test_enroll_and_graph(client):
    headers, uid = await _login(client, f"{_TAG}_{uuid.uuid4().hex[:8]}")
    n1, n2 = await _seed_textbook_and_pref(uid)
    try:
        # 显式纳入
        r = await client.post("/api/v1/student-kp/enroll", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["enrolled"] == 2

        # 默认地图:全集未练 → 不亮(items 空),summary in_scope=2
        r = await client.get("/api/v1/student-kp/graph", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["summary"]["in_scope"] == 2 and data["summary"]["practiced"] == 0
        assert len(data["items"]) == 0

        # 展开全集:含 2 个 unlearned
        r = await client.get("/api/v1/student-kp/graph?include_all=true", headers=headers)
        items = r.json()["data"]["items"]
        assert len(items) == 2 and all(it["status"] == "unlearned" for it in items)
        assert all("textbook" in it["source_tags"] for it in items)
    finally:
        await _cleanup(uid, n1, n2)


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.get("/api/v1/student-kp/graph")
    assert r.status_code in (401, 403)
