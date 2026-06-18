"""L7 长难句三源扩展:② textbook(平台 Passage)/ ③ uploaded(学生上传题→个人域)。

dev-mock 下 analyze_sentence 走确定性拆解;match_kp 命中预置「定语从句」node 挂边。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import Passage, UploadedQuestion
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services import long_sentence_service as lss
from app.services.kp_normalize import normalize_kp_name

_TAG = "lssrc"
LONG = ("The student who studies very hard every single day in the quiet library which "
        "is near the gate will surely pass the difficult final exam this year.")


@pytest_asyncio.fixture
async def db():
    async with _async_session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seed_node():
    """预置句法 node「定语从句」+ 别名,供 match_kp 挂边。"""
    nid = uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(KnowledgeNode(id=nid, axis="knowledge", node_kind="句法", name="定语从句",
                            code=f"{_TAG}-n", status="active", source="seed"))
        await s.flush()
        s.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias="定语从句",
                        alias_norm=normalize_kp_name("定语从句"), source="seed"))
        await s.commit()
    yield nid
    async with _async_session_factory() as s:
        await s.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(nid)})
        await s.execute(text("DELETE FROM knowledge_node_aliases WHERE node_id = :n"), {"n": str(nid)})
        await s.execute(text("DELETE FROM knowledge_nodes WHERE id = :n"), {"n": str(nid)})
        await s.commit()


async def _cleanup_ls(**where):
    col, val = next(iter(where.items()))
    async with _async_session_factory() as s:
        ids = (await s.execute(
            select(LongSentence.id).where(getattr(LongSentence, col) == val))).scalars().all()
        for lid in ids:
            await s.execute(text("DELETE FROM long_sentence_node WHERE long_sentence_id = :l"),
                            {"l": str(lid)})
        await s.execute(text(f"DELETE FROM long_sentence WHERE {col} = :v"), {"v": str(val)})
        await s.commit()


@pytest.mark.asyncio
async def test_extract_from_textbook_platform_scope(db, seed_node):
    """② 平台 Passage(reading_text)→ 平台域 textbook 长难句,挂句法 node。"""
    pid = uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(Passage(id=pid, scope="platform", kind="reading_text", text=LONG))
        await s.commit()
    try:
        st = await lss.extract_from_textbook(db, only_passage_ids={pid})
        assert st.created >= 1
        async with _async_session_factory() as s:
            ls = (await s.execute(select(LongSentence).where(
                LongSentence.source_passage_id == pid))).scalars().first()
            assert ls is not None
            assert ls.source_kind == "textbook"
            assert ls.scope == "platform"
            assert ls.owner_id is None
            edges = (await s.execute(select(LongSentenceNode).where(
                LongSentenceNode.long_sentence_id == ls.id))).scalars().all()
            assert len(edges) >= 1  # 定语从句挂边

        # 幂等:复跑跳过
        st2 = await lss.extract_from_textbook(db, only_passage_ids={pid})
        assert st2.skipped_done >= 1 and st2.created == 0
    finally:
        await _cleanup_ls(source_passage_id=pid)
        async with _async_session_factory() as s:
            await s.execute(text("DELETE FROM passage WHERE id = :p"), {"p": str(pid)})
            await s.commit()


@pytest.mark.asyncio
async def test_extract_from_uploaded_student_scope(db, seed_node):
    """③ 学生上传题 → 个人域 uploaded 长难句(owner_id=该生)。"""
    qid, owner = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(UploadedQuestion(id=qid, owner_scope="student", owner_id=owner, stem=LONG))
        await s.commit()
    try:
        st = await lss.extract_from_uploaded(db, owner_id=owner, only_question_ids={qid})
        assert st.created >= 1
        async with _async_session_factory() as s:
            ls = (await s.execute(select(LongSentence).where(
                LongSentence.source_question_id == qid))).scalars().first()
            assert ls is not None
            assert ls.source_kind == "uploaded"
            assert ls.scope == "student"
            assert ls.owner_id == owner
            assert ls.source_q_scope == "uploaded"
    finally:
        await _cleanup_ls(source_question_id=qid)
        async with _async_session_factory() as s:
            await s.execute(text("DELETE FROM uploaded_question WHERE id = :q"), {"q": str(qid)})
            await s.commit()


@pytest.mark.asyncio
async def test_run_extract_dispatches_multiple_sources(db, seed_node):
    """run_extract(sources=[...]) 合并多源统计。"""
    pid, qid, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as s:
        s.add(Passage(id=pid, scope="platform", kind="dialogue", text=LONG))
        s.add(UploadedQuestion(id=qid, owner_scope="student", owner_id=owner, stem=LONG))
        await s.commit()
    try:
        st = await lss.run_extract(db, sources=["textbook", "uploaded"])
        assert st.created >= 2  # 两源各 ≥1
    finally:
        await _cleanup_ls(source_passage_id=pid)
        await _cleanup_ls(source_question_id=qid)
        async with _async_session_factory() as s:
            await s.execute(text("DELETE FROM passage WHERE id = :p"), {"p": str(pid)})
            await s.execute(text("DELETE FROM uploaded_question WHERE id = :q"), {"q": str(qid)})
            await s.commit()
