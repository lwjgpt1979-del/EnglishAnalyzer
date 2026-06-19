"""L5 长难句后台:抽取触发 / 审核列表+发布 / 配置读写 / 非超管403。"""
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
from app.models.d16_question_domain import PlatformQuestion
from app.models.d20_long_sentence import LongSentence
from app.services.kp_normalize import normalize_kp_name

_TAG = "lsadm"
LONG = ("The student who studies very hard every single day in the quiet library which "
        "is near the gate will surely pass the difficult final exam this year.")


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


async def _seed():
    """E1 受控树已 seed「定语从句」→ 复用既有节点(不重复建);否则新建。"""
    pq_id = uuid.uuid4()
    norm = normalize_kp_name("定语从句")
    async with _async_session_factory() as db:
        existing = (await db.execute(
            select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm))).scalar_one_or_none()
        if existing is not None:
            node_id = existing
        else:
            node_id = uuid.uuid4()
            db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                                 code=f"{_TAG}-n", status="active", source="seed"))
            await db.flush()
            db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias="定语从句",
                             alias_norm=norm, source="seed"))
        db.add(PlatformQuestion(id=pq_id, type="real", question_type="阅读", stem=LONG, status="published"))
        await db.commit()
    return node_id, pq_id


async def _cleanup(node_id, pq_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE source_question_id = :q"), {"q": str(pq_id)})
        await db.execute(text("DELETE FROM platform_question WHERE id = :q"), {"q": str(pq_id)})
        # 仅清本测试可能新建的节点(code 带 _TAG);复用的受控树节点不动
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE node_id IN "
                              "(SELECT id FROM knowledge_nodes WHERE code LIKE :p)"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_extract_review_config(client):
    node_id, pq_id = await _seed()
    try:
        admin = await _make_admin(client, "a")
        # 抽取触发
        r = await client.post("/api/v1/admin/long-sentences/extract?limit=200", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["created"] >= 1

        # 我的句子已抽、draft 在审核列表
        async with _async_session_factory() as db:
            ls = (await db.execute(select(LongSentence).where(
                LongSentence.source_question_id == pq_id))).scalar_one()
            ls_id = ls.id
            assert ls.status == "draft"
        r = await client.get(f"/api/v1/admin/long-sentences?status=draft&node_id={node_id}", headers=admin)
        assert any(it["id"] == str(ls_id) for it in r.json()["data"]["items"])

        # 审核发布
        r = await client.post(f"/api/v1/admin/long-sentences/{ls_id}/review",
                              json={"approve": True}, headers=admin)
        assert r.json()["data"]["status"] == "published"

        # 配置读写
        r = await client.get("/api/v1/admin/long-sentences/config", headers=admin)
        assert r.json()["data"]["sources"] == ["platform_real"]
        r = await client.put("/api/v1/admin/long-sentences/config",
                            json={"min_words": 25, "required_pass": 2}, headers=admin)
        d = r.json()["data"]
        assert d["min_words"] == 25 and d["required_pass"] == 2
    finally:
        await _cleanup(node_id, pq_id)
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM system_configs WHERE key LIKE 'long_sentence.%'"))
            await db.commit()


@pytest.mark.asyncio
async def test_extract_by_source_textbook_and_uploaded(client):
    """L7:extract?source=textbook 抽平台语料、source=uploaded 抽学生上传。"""
    from app.models.d16_question_domain import Passage, UploadedQuestion
    from app.models.d20_long_sentence import LongSentence
    node_id, _pq = await _seed()  # 复用「定语从句」node 挂边
    pid, qid, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(Passage(id=pid, scope="platform", kind="reading_text", text=LONG))
        db.add(UploadedQuestion(id=qid, owner_scope="student", owner_id=owner, stem=LONG))
        await db.commit()
    try:
        admin = await _make_admin(client, "src")
        r = await client.post("/api/v1/admin/long-sentences/extract?source=textbook&limit=200", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["created"] >= 1
        r = await client.post("/api/v1/admin/long-sentences/extract?source=uploaded&limit=200", headers=admin)
        assert r.json()["data"]["created"] >= 1

        async with _async_session_factory() as db:
            tb = (await db.execute(select(LongSentence).where(
                LongSentence.source_passage_id == pid))).scalars().first()
            up = (await db.execute(select(LongSentence).where(
                LongSentence.source_question_id == qid))).scalars().first()
            assert tb is not None and tb.source_kind == "textbook" and tb.scope == "platform"
            assert up is not None and up.source_kind == "uploaded" and up.scope == "student"

        # 非法 source
        r = await client.post("/api/v1/admin/long-sentences/extract?source=bogus", headers=admin)
        assert r.status_code == 400
    finally:
        async with _async_session_factory() as db:
            for col, val in (("source_passage_id", pid), ("source_question_id", qid)):
                ids = (await db.execute(select(LongSentence.id).where(
                    getattr(LongSentence, col) == val))).scalars().all()
                for lid in ids:
                    await db.execute(text("DELETE FROM long_sentence_node WHERE long_sentence_id = :l"),
                                     {"l": str(lid)})
                await db.execute(text(f"DELETE FROM long_sentence WHERE {col} = :v"), {"v": str(val)})
            await db.execute(text("DELETE FROM passage WHERE id = :p"), {"p": str(pid)})
            await db.execute(text("DELETE FROM uploaded_question WHERE id = :q"), {"q": str(qid)})
            await db.commit()
        await _cleanup(node_id, _pq)


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    stu = await _login(client, f"{_TAG}_stu_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/long-sentences?status=draft", headers=stu)
    assert r.status_code == 403
