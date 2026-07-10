"""R1.4 教材对齐 HTTP:重跑对齐(命中建边/未命中候选)+ 查看单元节点 + 非超管 403。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import normalize_kp_name

_TAG = "ckhttp"
HIT = f"{_TAG}一般现在时"
MISS = f"{_TAG}独有概念xyz"


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


async def _seed():
    """R8:单元已挂图谱节点(unit_node 取材源)——HIT 有别名(可重匹配)/MISS 无别名(落候选)。

    reextract_unit 从 unit_node → knowledge_nodes 取名再受控匹配:HIT 命中(边已存在→不新增),
    MISS 无别名→落候选(带 unit 来源)。返回 (unit_id, hit_node_id)。
    """
    unit_id, hit_id, miss_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="初中7年级",
                             semester="上", unit_no=1, unit_title=f"{_TAG}U1"))
        s.add(KnowledgeNode(id=hit_id, axis="knowledge", node_kind="句法", name=HIT,
                            code=f"{_TAG}-hit", status="active", source="textbook",
                            applicable_stages=["初"]))
        s.add(KnowledgeNode(id=miss_id, axis="knowledge", node_kind="句法", name=MISS,
                            code=f"{_TAG}-miss", status="active", source="textbook",
                            applicable_stages=["初"]))
        await s.flush()
        s.add(NodeAlias(id=uuid.uuid4(), node_id=hit_id, alias=HIT,
                        alias_norm=normalize_kp_name(HIT), source="seed"))
        # 两个节点都挂到单元(reextract 从 unit_node 取材)
        s.add(UnitNode(unit_id=unit_id, node_id=hit_id, source="seed"))
        s.add(UnitNode(unit_id=unit_id, node_id=miss_id, source="seed"))
        await s.commit()
    return unit_id, hit_id


async def _cleanup(unit_id):
    async with _async_session_factory() as s:
        await s.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
        await s.execute(text("DELETE FROM kp_candidates WHERE name_norm LIKE :p"), {"p": f"{_TAG}%"})
        await s.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await s.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await s.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :v"), {"v": f"{_TAG}版"})
        await s.commit()


@pytest.mark.asyncio
async def test_reextract_and_list_unit_nodes(client):
    unit_id, node_id = await _seed()
    try:
        admin = await _make_admin(client, "a")
        # 重跑对齐(R8:从 unit_node 取材):HIT 命中别名(边已存在→不新增)、MISS 无别名落候选
        r = await client.post(f"/api/v1/admin/curriculum/units/{unit_id}/extract-kps", headers=admin)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data == {"matched": 1, "candidate": 1, "edges_created": 0}

        # 查看单元节点:两条 unit_node 边(HIT + MISS 均已挂),含 HIT
        r = await client.get(f"/api/v1/admin/curriculum/units/{unit_id}/nodes", headers=admin)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 2
        hit = next(it for it in items if it["node_id"] == str(node_id))
        assert hit["name"] == HIT

        # MISS 落候选,带 unit 来源
        async with _async_session_factory() as s:
            cand = (await s.execute(select(KpCandidate).where(KpCandidate.raw_name == MISS))).scalar_one()
            assert str(unit_id) in (cand.source_ref or {}).get("unit_ids", [])
    finally:
        await _cleanup(unit_id)


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    unit_id, _ = await _seed()
    try:
        stu = await _login_as(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
        r = await client.post(f"/api/v1/admin/curriculum/units/{unit_id}/extract-kps", headers=stu)
        assert r.status_code == 403
        r = await client.get(f"/api/v1/admin/curriculum/units/{unit_id}/nodes", headers=stu)
        assert r.status_code == 403
    finally:
        await _cleanup(unit_id)
