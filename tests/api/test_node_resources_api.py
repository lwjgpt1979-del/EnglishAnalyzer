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


@pytest.mark.asyncio
async def test_lecture_versioning_no_overwrite(client):
    """C1:覆盖已发布讲解 → 产生 pending 版本,线上内容不变。"""
    node_id = await _seed_node()
    try:
        admin = await _make_admin(client, "ver")
        # 首铺一条 published 讲解(直发)
        r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
            "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
            "content_md": "原始语法讲解 v1", "status": "published"})
        assert r.status_code == 200, r.text
        rid = r.json()["data"]["id"]

        # 再次提交同维度新内容 → 不应覆盖线上,而是产生 pending 版本
        r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
            "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
            "content_md": "重写后的语法讲解 v2", "status": "published"})
        assert r.status_code == 200, r.text

        async with _async_session_factory() as db:
            # 线上内容仍是 v1(未被覆盖)
            live = (await db.execute(text(
                "SELECT content_md, status FROM node_resource WHERE id = :i"), {"i": rid})).first()
            assert live[0] == "原始语法讲解 v1" and live[1] == "published"
            # 版本表:v1=published(首铺直发),v2=pending(待审新版)
            vrows = (await db.execute(text(
                "SELECT version_no, status, content_md FROM node_resource_version "
                "WHERE resource_id = :i ORDER BY version_no"), {"i": rid})).all()
            assert len(vrows) == 2
            assert vrows[0][1] == "published" and vrows[0][2] == "原始语法讲解 v1"
            assert vrows[1][1] == "pending" and vrows[1][2] == "重写后的语法讲解 v2"
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM node_resource_version WHERE node_id = :n"), {"n": str(node_id)})
            await db.commit()
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_version_diff_approve_reject(client):
    """C2:待审版本 diff + approve 替换线上&归档旧版 + reject 线上不变。"""
    node_id = await _seed_node()
    try:
        admin = await _make_admin(client, "c2")

        async def _submit(content):
            r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
                "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
                "content_md": content, "status": "published"})
            assert r.status_code == 200, r.text
            return r.json()["data"]["id"]

        rid = await _submit("v1 正文")           # 首铺 published
        await _submit("v2 正文")                  # 覆盖已发布 → 产生 pending v2

        # 取 pending 版本 id
        async with _async_session_factory() as db:
            vid = (await db.execute(text(
                "SELECT id FROM node_resource_version WHERE resource_id=:r AND status='pending'"),
                {"r": rid})).scalar()

        # diff(against current)
        r = await client.get(f"/api/v1/admin/node-resource-versions/{vid}/diff", headers=admin)
        d = r.json()["data"]
        assert d["base"]["content_md"] == "v1 正文" and d["incoming"]["content_md"] == "v2 正文"

        # 先验证 reject 不动线上
        await _submit("v3 正文")                  # 再产生一个 pending v3
        async with _async_session_factory() as db:
            vid3 = (await db.execute(text(
                "SELECT id FROM node_resource_version WHERE resource_id=:r AND status='pending' "
                "ORDER BY version_no DESC LIMIT 1"), {"r": rid})).scalar()
        r = await client.post(f"/api/v1/admin/node-resource-versions/{vid3}/reject", headers=admin)
        assert r.status_code == 200, r.text
        async with _async_session_factory() as db:
            live = (await db.execute(text("SELECT content_md FROM node_resource WHERE id=:i"), {"i": rid})).scalar()
            assert live == "v1 正文"              # 驳回后线上仍 v1

        # approve v2 → 线上变 v2,v1 归档,v2 published
        r = await client.post(f"/api/v1/admin/node-resource-versions/{vid}/approve", headers=admin)
        assert r.status_code == 200, r.text
        async with _async_session_factory() as db:
            live = (await db.execute(text("SELECT content_md, status FROM node_resource WHERE id=:i"), {"i": rid})).first()
            assert live[0] == "v2 正文" and live[1] == "published"
            statuses = dict((await db.execute(text(
                "SELECT content_md, status FROM node_resource_version WHERE resource_id=:r"), {"r": rid})).all())
            assert statuses["v1 正文"] == "archived"
            assert statuses["v2 正文"] == "published"
            assert statuses["v3 正文"] == "rejected"
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM node_resource_version WHERE node_id = :n"), {"n": str(node_id)})
            await db.commit()
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_version_history_and_rollback(client):
    """C3:版本历史列表 + 回滚(把归档版重新提升为线上)。"""
    node_id = await _seed_node()
    try:
        admin = await _make_admin(client, "c3")

        async def _submit(content):
            r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
                "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
                "content_md": content, "status": "published"})
            assert r.status_code == 200, r.text
            return r.json()["data"]["id"]

        rid = await _submit("内容 v1")          # published
        await _submit("内容 v2")                 # pending v2
        async with _async_session_factory() as db:
            vid2 = (await db.execute(text(
                "SELECT id FROM node_resource_version WHERE resource_id=:r AND status='pending'"),
                {"r": rid})).scalar()
        # 通过 v2 → 线上=v2,v1 归档
        await client.post(f"/api/v1/admin/node-resource-versions/{vid2}/approve", headers=admin)

        # 历史列表:2 版,倒序 v2(published)/v1(archived)
        r = await client.get(f"/api/v1/admin/node-resources/{rid}/versions", headers=admin)
        items = r.json()["data"]["items"]
        assert [it["version_no"] for it in items] == [2, 1]
        v1 = next(it for it in items if it["version_no"] == 1)
        assert v1["status"] == "archived"

        # 回滚到 v1 → 线上变回 v1,v2 归档
        r = await client.post(f"/api/v1/admin/node-resources/{rid}/rollback/{v1['id']}", headers=admin)
        assert r.status_code == 200, r.text
        async with _async_session_factory() as db:
            live = (await db.execute(text("SELECT content_md FROM node_resource WHERE id=:i"), {"i": rid})).scalar()
            assert live == "内容 v1"
            st = dict((await db.execute(text(
                "SELECT content_md, status FROM node_resource_version WHERE resource_id=:r"), {"r": rid})).all())
            assert st["内容 v1"] == "published" and st["内容 v2"] == "archived"

        # 当前线上版本不可回滚
        r = await client.post(f"/api/v1/admin/node-resources/{rid}/rollback/{v1['id']}", headers=admin)
        assert r.status_code == 400
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM node_resource_version WHERE node_id = :n"), {"n": str(node_id)})
            await db.commit()
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_unit_filter_and_content_overview(client):
    """A 期:按 unit_id 过滤 node-resources + 单元补全总览(六维缺失)。"""
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d17_curriculum_kg import UnitNode
    node_id = await _seed_node()
    unit_id = uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(CurriculumUnit(id=unit_id, textbook_version=f"{_TAG}版", grade="七年级",
                              semester="下", unit_no=1, unit_title=f"{_TAG}单元"))
        await db.flush()
        db.add(UnitNode(unit_id=unit_id, node_id=node_id, source="manual"))
        await db.commit()
    try:
        admin = await _make_admin(client, "ov")
        # 只给 grammar 维度建讲解 → 其余 5 维缺失
        r = await client.post("/api/v1/admin/node-resources", headers=admin, json={
            "node_id": str(node_id), "resource_type": "lecture", "dimension": "grammar",
            "content_md": "语法", "status": "draft"})
        assert r.status_code == 200, r.text

        # 按 unit_id 过滤(全状态)→ 命中 1 条,且带 node_name
        r = await client.get(f"/api/v1/admin/node-resources?unit_id={unit_id}&status=", headers=admin)
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["node_name"] == f"{_TAG}KP"

        # 补全总览:1 节点,grammar=draft,其余 5 维为 null
        r = await client.get(f"/api/v1/admin/curriculum/units/{unit_id}/content-overview", headers=admin)
        ov = r.json()["data"]
        assert ov["total_nodes"] == 1
        dims = ov["items"][0]["dims"]
        assert dims["grammar"]["status"] == "draft"
        assert dims["listening"] is None and dims["writing"] is None
        assert sum(1 for d in dims.values() if d is None) == 5

        # B 期:一键发布整单元 → grammar 草稿转 published,仍缺 5 维
        r = await client.post(f"/api/v1/admin/curriculum/units/{unit_id}/publish", headers=admin)
        assert r.status_code == 200, r.text
        pub = r.json()["data"]
        assert pub["published"] == 1 and pub["missing_dims"] == 5
        # 学生现在能读到该 published 讲解
        stu = await _login(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
        r = await client.get(f"/api/v1/curriculum/nodes/{node_id}/resources", headers=stu)
        assert any(it["dimension"] == "grammar" for it in r.json()["data"]["items"])
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM unit_node WHERE unit_id = :u"), {"u": str(unit_id)})
            await db.execute(text("DELETE FROM curriculum_units WHERE id = :u"), {"u": str(unit_id)})
            await db.commit()
        await _cleanup(node_id)
