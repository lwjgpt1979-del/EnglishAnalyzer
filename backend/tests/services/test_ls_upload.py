"""上传长难句:挂靠到知识图谱(限 cf/jf)、改挂、新建节点、别称沉淀、列出、删除。"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services import long_sentence_upload_service as lsu


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _ensure_jf_root(db) -> KnowledgeNode:
    root = (await db.execute(sa.select(KnowledgeNode).where(KnowledgeNode.code == "jf"))).scalar_one_or_none()
    if root is None:
        root = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", name="句法", code="jf",
                             status="active", source="seed")
        db.add(root)
        await db.flush()
    return root


def _mk_ls(point: str, text: str) -> LongSentence:
    return LongSentence(id=uuid.uuid4(), scope="platform", source_kind="uploaded", status="draft",
                        text=text, difficulty=60, analysis_json={"syntax_points": [point], "source": "upload"})


@pytest.mark.asyncio
async def test_link_records_alias_and_relink(db_session):
    root = await _ensure_jf_root(db_session)
    child = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", parent_id=root.id, name="定语从句",
                          code=f"jf-{uuid.uuid4().hex[:6]}", status="active", source="manual")
    other = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", parent_id=root.id, name="宾语从句",
                          code=f"jf-{uuid.uuid4().hex[:6]}", status="active", source="manual")
    db_session.add_all([child, other])
    point = f"定语从句{uuid.uuid4().hex[:6]}"
    ls = _mk_ls(point, "The book that I read is good.")
    db_session.add(ls)
    await db_session.flush()

    r = await lsu.link_node(db_session, ls_id=ls.id, node_id=child.id)
    assert r["node_code"] == child.code
    # 挂边
    edge = (await db_session.execute(sa.select(LongSentenceNode.node_id)
            .where(LongSentenceNode.long_sentence_id == ls.id))).scalars().all()
    assert edge == [child.id]
    # 语法点名沉淀为别称 → child
    aid = (await db_session.execute(sa.select(NodeAlias.node_id).where(NodeAlias.alias == point))).scalar_one_or_none()
    assert aid == child.id

    # 改挂到另一个节点 → 替换挂边(不重复)
    await lsu.link_node(db_session, ls_id=ls.id, node_id=other.id)
    edge2 = (await db_session.execute(sa.select(LongSentenceNode.node_id)
             .where(LongSentenceNode.long_sentence_id == ls.id))).scalars().all()
    assert edge2 == [other.id]


@pytest.mark.asyncio
async def test_link_rejects_non_grammar_subtree(db_session):
    # 听力根 lt 下的节点不在 cf/jf,应被拒绝
    lt = (await db_session.execute(sa.select(KnowledgeNode).where(KnowledgeNode.code == "lt"))).scalar_one_or_none()
    if lt is None:
        lt = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", name="听力", code="lt", status="active", source="seed")
        db_session.add(lt)
        await db_session.flush()
    ls = _mk_ls("x", "Some sentence here.")
    db_session.add(ls)
    await db_session.flush()
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        await lsu.link_node(db_session, ls_id=ls.id, node_id=lt.id)


@pytest.mark.asyncio
async def test_new_node_and_list_and_delete(db_session):
    root = await _ensure_jf_root(db_session)
    point = f"强调句{uuid.uuid4().hex[:6]}"
    ls = _mk_ls(point, "It is here that we met.")
    db_session.add(ls)
    await db_session.flush()

    r = await lsu.new_node(db_session, ls_id=ls.id, parent_id=root.id, name=point)
    assert r["node_code"].startswith("m-")
    # 新建节点已挂边 + 在列表里
    recent = await lsu.list_recent(db_session, limit=100)
    row = next((x for x in recent if x["id"] == str(ls.id)), None)
    assert row and row["point"] == point and row["node_code"] == r["node_code"]

    await lsu.delete_uploaded(db_session, ls_id=ls.id)
    gone = (await db_session.execute(sa.select(LongSentence.id).where(LongSentence.id == ls.id))).scalar_one_or_none()
    assert gone is None
