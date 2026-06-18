"""L2 长难句学生端:列表 / 解析详情(主干分层/译文/句法点node)/ 未发布404 / 鉴权。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d20_long_sentence import LongSentence, LongSentenceNode

_TAG = "lsapi"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _seed():
    node_id, pub_id, draft_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}定从",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(LongSentence(id=pub_id, scope="platform", source_kind="platform_real",
                            text="The book which covers grammar is useful.",
                            analysis_json={"main_clause": "The book is useful",
                                           "layers": [{"type": "定语从句", "text": "which covers grammar"}],
                                           "translation": "[译] 这本…", "syntax_points": ["定语从句"]},
                            status="published"))
        db.add(LongSentence(id=draft_id, scope="platform", source_kind="platform_real",
                            text="draft sentence", status="draft"))
        await db.flush()
        db.add(LongSentenceNode(long_sentence_id=pub_id, node_id=node_id))
        await db.commit()
    return node_id, pub_id, draft_id


async def _cleanup(node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE text LIKE :p OR source_kind = 'platform_real' "
                              "AND text IN ('draft sentence')"), {"p": "The book which covers%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_list_and_detail(client):
    node_id, pub_id, draft_id = await _seed()
    try:
        h = await _login(client, f"{_TAG}_{uuid.uuid4().hex[:6]}")
        # 列表(按 node 过滤)→ 只见已发布
        r = await client.get(f"/api/v1/long-sentences?node_id={node_id}", headers=h)
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        ids = {it["id"] for it in items}
        assert str(pub_id) in ids and str(draft_id) not in ids
        assert any(it["syntax_points"] == ["定语从句"] for it in items)

        # 详情:解析 + 句法点 node(供跳 R6 资源)
        r = await client.get(f"/api/v1/long-sentences/{pub_id}", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["analysis"]["main_clause"] == "The book is useful"
        assert d["analysis"]["translation"].startswith("[译]")
        assert len(d["nodes"]) == 1 and d["nodes"][0]["node_id"] == str(node_id)

        # 未发布 → 404
        r = await client.get(f"/api/v1/long-sentences/{draft_id}", headers=h)
        assert r.status_code == 404
    finally:
        await _cleanup(node_id)


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.get("/api/v1/long-sentences")
    assert r.status_code in (401, 403)
