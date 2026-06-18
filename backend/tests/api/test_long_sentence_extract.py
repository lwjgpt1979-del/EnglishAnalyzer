"""L1 长难句抽取:长句判定 + 平台真题抽取(AI拆解→挂句法node)+ 幂等。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, func, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion
from app.models.d20_long_sentence import LongSentence, LongSentenceNode
from app.services.kp_normalize import normalize_kp_name
from app.services import long_sentence_service as lss

_TAG = "lsext"
# ≥20 词 + 含 which/that → 定语从句(长难句)
LONG = ("The book that the teacher recommended to all the students in our class last "
        "week which covers advanced grammar is extremely useful for the final exam.")
SHORT = "I like apples."


def test_is_long_sentence():
    assert lss.is_long_sentence(LONG) is True
    assert lss.is_long_sentence(SHORT) is False
    # 够长但无结构信号 → 非长难句
    plain = " ".join(["word"] * 25)
    assert lss.is_long_sentence(plain) is False


async def _seed():
    node_id, pq_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                             code=f"{_TAG}-dingyu", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias="定语从句",
                         alias_norm=normalize_kp_name("定语从句"), source="seed"))
        db.add(PlatformQuestion(id=pq_id, type="real", question_type="阅读",
                                stem=LONG + " " + SHORT, status="published"))
        await db.commit()
    return node_id, pq_id


async def _cleanup(node_id, pq_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE source_question_id = :q"), {"q": str(pq_id)})
        await db.execute(text("DELETE FROM platform_question WHERE id = :q"), {"q": str(pq_id)})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm = :a"),
                         {"a": normalize_kp_name("定语从句")})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_extract_from_platform_and_idempotent():
    node_id, pq_id = await _seed()
    try:
        async with _async_session_factory() as db:
            st = await lss.extract_from_platform(db, only_question_ids={pq_id})
            assert st.created == 1 and st.long_kept == 1   # 只 LONG 是长难句,SHORT 被滤
            assert st.edges == 1 and "定语从句" in st.syntax_points

        async with _async_session_factory() as db:
            ls = (await db.execute(select(LongSentence).where(
                LongSentence.source_question_id == pq_id))).scalar_one()
            assert ls.text.startswith("The book") and ls.source_kind == "platform_real"
            assert ls.analysis_json["syntax_points"] == ["定语从句"]
            assert ls.analysis_json["main_clause"]    # 主干非空(dev mock)
            edge = (await db.execute(select(LongSentenceNode).where(
                LongSentenceNode.long_sentence_id == ls.id))).scalar_one()
            assert edge.node_id == node_id

        # 幂等:复跑该真题已抽 → 跳过,不新增
        async with _async_session_factory() as db:
            st2 = await lss.extract_from_platform(db, only_question_ids={pq_id})
            assert st2.created == 0 and st2.skipped_done == 1
            cnt = (await db.execute(select(func.count()).select_from(LongSentence)
                   .where(LongSentence.source_question_id == pq_id))).scalar_one()
            assert cnt == 1
    finally:
        await _cleanup(node_id, pq_id)
