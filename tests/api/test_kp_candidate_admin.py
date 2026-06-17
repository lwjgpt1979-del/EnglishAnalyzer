"""R0.4 候选知识点审核 HTTP 测试:approve / merge别名 / reject + 非超管 403。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.services.kp_normalize import normalize_kp_name

_TAG = "kpcadm"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client: AsyncClient, openid: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_admin(client: AsyncClient, suffix: str) -> dict:
    openid = f"{_TAG}_adm_{suffix}"
    headers = await _login_as(client, openid)
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.openid == openid))).scalar_one()
        u.role = "platform_admin"  # type: ignore[assignment]
        await s.commit()
    return headers


async def _seed_candidate(name: str) -> uuid.UUID:
    cid = uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(KpCandidate(
            id=cid, raw_name=name, name_norm=normalize_kp_name(name),
            suggested_axis="knowledge", suggested_stage="初", occur_count=3,
            source_type="exam", status="pending",
        ))
        await s.commit()
    return cid


async def _seed_node(name: str) -> uuid.UUID:
    nid = uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(KnowledgeNode(
            id=nid, axis="knowledge", node_kind="句法", name=name,
            code=f"{_TAG}-{uuid.uuid4().hex[:6]}", status="active", source="seed",
        ))
        await s.flush()
        s.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=name,
                        alias_norm=normalize_kp_name(name), source="seed"))
        await s.commit()
    return nid


async def _cleanup():
    async with _async_session_factory() as s:
        await s.execute(text("DELETE FROM kp_candidates WHERE raw_name LIKE :p"), {"p": f"{_TAG}%"})
        await s.execute(text("DELETE FROM knowledge_node_aliases WHERE alias LIKE :p"), {"p": f"{_TAG}%"})
        await s.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await s.commit()


@pytest.mark.asyncio
async def test_approve_creates_node_and_alias(client):
    cid = await _seed_candidate(f"{_TAG}过去完成时")
    try:
        admin = await _make_admin(client, "a")
        # 列表能看到该候选
        r = await client.get("/api/v1/admin/kp-candidates?status=pending", headers=admin)
        assert r.status_code == 200
        assert any(it["id"] == str(cid) for it in r.json()["data"]["items"])

        r = await client.post(
            f"/api/v1/admin/kp-candidates/{cid}/approve",
            json={"axis": "knowledge", "stage": "初", "node_kind": "句法"},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        node_id = uuid.UUID(r.json()["data"]["id"])

        async with _async_session_factory() as s:
            node = (await s.execute(select(KnowledgeNode).where(KnowledgeNode.id == node_id))).scalar_one()
            assert node.status == "active" and node.axis == "knowledge"
            assert node.applicable_stages == ["初"]
            alias = (await s.execute(
                select(NodeAlias).where(NodeAlias.node_id == node_id)
            )).scalar_one()
            assert alias.alias == f"{_TAG}过去完成时"
            cand = (await s.execute(select(KpCandidate).where(KpCandidate.id == cid))).scalar_one()
            assert cand.status == "approved" and cand.merged_into_node_id == node_id
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_merge_adds_alias_to_target(client):
    target_id = await _seed_node(f"{_TAG}过去完成时")
    cid = await _seed_candidate(f"{_TAG}过去完成时态")  # 同义异写 → 应并为别名
    try:
        admin = await _make_admin(client, "m")
        r = await client.post(
            f"/api/v1/admin/kp-candidates/{cid}/merge",
            json={"target_node_id": str(target_id)},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        assert uuid.UUID(r.json()["data"]["id"]) == target_id

        async with _async_session_factory() as s:
            aliases = (await s.execute(
                select(NodeAlias.alias).where(NodeAlias.node_id == target_id)
            )).scalars().all()
            assert f"{_TAG}过去完成时态" in aliases   # 候选名并入目标别名
            cand = (await s.execute(select(KpCandidate).where(KpCandidate.id == cid))).scalar_one()
            assert cand.status == "merged" and cand.merged_into_node_id == target_id
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_reject_records_reason(client):
    cid = await _seed_candidate(f"{_TAG}无意义噪声")
    try:
        admin = await _make_admin(client, "r")
        r = await client.post(
            f"/api/v1/admin/kp-candidates/{cid}/reject",
            json={"reason": "OCR 噪声,非知识点"},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        async with _async_session_factory() as s:
            cand = (await s.execute(select(KpCandidate).where(KpCandidate.id == cid))).scalar_one()
            assert cand.status == "rejected"
            assert cand.context_sample.get("reject_reason") == "OCR 噪声,非知识点"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    cid = await _seed_candidate(f"{_TAG}权限测试")
    try:
        student = await _login_as(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
        r = await client.post(
            f"/api/v1/admin/kp-candidates/{cid}/approve",
            json={"axis": "knowledge"}, headers=student,
        )
        assert r.status_code == 403
    finally:
        await _cleanup()
