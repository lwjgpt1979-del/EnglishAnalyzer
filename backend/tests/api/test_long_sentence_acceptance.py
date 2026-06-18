"""长难句 验收闭环:平台真题→抽取(挂句法node)→审核发布→学生读解析→验证连对判句法node掌握。

串起 L1 抽取 / L5 审核 / L2 读取 / L3 验证 + R3/R4 判掌握回写,印证"来源→理解→验证学会"一条龙。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
from app.models.d16_question_domain import PlatformQuestion, StudentKp
from app.models.d20_long_sentence import LongSentence
from app.services.kp_normalize import normalize_kp_name
from app.services import long_sentence_service as lss

_TAG = "lsacc"
LONG = ("The novel that my elder sister bought online last month which describes a long "
        "journey across the desert has become quite popular among young readers recently.")


async def _seed():
    node_id, pq_id = uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name="定语从句",
                             code=f"{_TAG}-n", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=node_id, alias="定语从句",
                         alias_norm=normalize_kp_name("定语从句"), source="seed"))
        db.add(PlatformQuestion(id=pq_id, type="real", question_type="阅读", stem=LONG, status="published"))
        await db.commit()
    return node_id, pq_id


async def _cleanup(node_id, pq_id, *students):
    async with _async_session_factory() as db:
        for s in students:
            await db.execute(text("DELETE FROM answer_log WHERE student_id = :s"), {"s": str(s)})
            await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(s)})
            await db.execute(text("DELETE FROM student_kp WHERE student_id = :s"), {"s": str(s)})
        await db.execute(text("DELETE FROM long_sentence_node WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM long_sentence WHERE source_question_id = :q"), {"q": str(pq_id)})
        await db.execute(text("DELETE FROM platform_question WHERE id = :q"), {"q": str(pq_id)})
        await db.execute(text("DELETE FROM knowledge_node_aliases WHERE alias_norm = :a"),
                         {"a": normalize_kp_name("定语从句")})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_long_sentence_full_loop():
    node_id, pq_id = await _seed()
    student = uuid.uuid4()
    try:
        # ① 来源→抽取:平台真题 → 长难句(draft)+ 挂句法 node
        async with _async_session_factory() as db:
            st = await lss.extract_from_platform(db, only_question_ids={pq_id})
            assert st.created == 1 and st.edges == 1
            ls = (await db.execute(select(LongSentence).where(
                LongSentence.source_question_id == pq_id))).scalar_one()
            ls_id = ls.id
            assert ls.status == "draft"

        # ② 审核发布
        async with _async_session_factory() as db:
            await lss.review(db, ls_id=ls_id, approve=True)
            await db.commit()

        # ③ 理解:学生读到已发布长难句 + 解析 + 句法点 node(供跳 R6 讲解)
        async with _async_session_factory() as db:
            pub = await lss.list_published(db, node_id=node_id, owner_id=student)
            assert any(x.id == ls_id for x in pub)
            ls2, nodes = await lss.get_detail(db, ls_id=ls_id)
            assert ls2.analysis_json.get("main_clause")
            assert nodes and nodes[0]["node_id"] == node_id and nodes[0]["name"] == "定语从句"

        # ④ 验证学会:结构题连对 3 次 → 判句法 node 掌握(进个人图谱)
        async with _async_session_factory() as db:
            for _ in range(3):
                r = await lss.submit_verify(db, student_id=student, ls_id=ls_id,
                                            verify_type="struct_type", answer="定语从句")
            await db.commit()
            assert r["mastered_nodes"] == ["定语从句"]
        async with _async_session_factory() as db:
            sk = (await db.execute(select(StudentKp).where(
                StudentKp.student_id == student, StudentKp.node_id == node_id))).scalar_one()
            assert float(sk.mastery) == 1.0   # 长难句"学会" = 句法 node 在个人图谱判掌握
    finally:
        await _cleanup(node_id, pq_id, student)
