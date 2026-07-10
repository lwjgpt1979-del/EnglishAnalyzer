"""curriculum_service.persist_unit 幂等性 + paywall 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d4_knowledge import (  # R8:KnowledgePoint/UnitKnowledgePoint 已退役,单元知识点=unit_node 边
    CurriculumUnit,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.schemas.curriculum import AIGeneratedUnit, AIKnowledgePointItem, AIWordItem
from app.services import curriculum_ai_service, curriculum_service


async def _seed_kp_nodes(db, names, *, axis="knowledge"):
    """E2:为给定知识点名建受控树节点+别名(幂等)。模拟"后台已定义的树",
    使 persist_unit 的 match_kp 能命中并挂内容。"""
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.services.kp_normalize import normalize_kp_name
    ids = {}
    for nm in names:
        if not nm or not nm.strip():
            continue
        norm = normalize_kp_name(nm)
        exists = (await db.execute(
            select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm))).scalar_one_or_none()
        if exists is not None:
            ids[nm] = exists
            continue
        nid = uuid.uuid4()
        db.add(KnowledgeNode(id=nid, axis=axis, name=nm, code=f"ttree-{uuid.uuid4().hex[:8]}",
                             status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=nm,
                         alias_norm=normalize_kp_name(nm), source="seed"))
        await db.flush()
        ids[nm] = nid
    return ids


def _make_unique_unit() -> AIGeneratedUnit:
    """构造一个 code 含唯一 nonce 的 mock 单元。

    dev-mock 的 generate_unit 输出 code 固定（按 grade/sem/unit 派生），多次跑
    测试时历史已提交的 KnowledgePoint 会被本测试按 code 查回并计入断言，导致计数
    被污染。这里给每个 code 加 uuid 后缀，确保 found_kps 只命中本次新建的 KP。
    """
    nonce = uuid.uuid4().hex[:8]
    return AIGeneratedUnit(
        textbook_version="译林版",
        grade="小学5年级",
        semester="上",
        unit_no=1,
        unit_title=f"Unit 1 ({nonce})",
        knowledge_points=[
            AIKnowledgePointItem(
                code=f"test-{nonce}-kp{i}",
                name=f"知识点 {i}（mock）",
                category="grammar",
                description="占位描述：测试 mock 数据",
            )
            for i in range(1, 4)
        ],
        words=[
            AIWordItem(
                word=f"word-{nonce}-{i}",
                phonetic=f"/w{i}/",
                definitions=[{"pos": "n.", "meaning": f"mock 释义{i}"}],
                examples=[],
                difficulty=1,
            )
            for i in range(1, 6)
        ],
    )


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时 generate_unit 打到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_persist_unit_creates_all_6_tables(db_session):
    """E2:受控树已有匹配节点时,persist_unit 映射上树——建 unit_node 边 + 挂六维讲解 + 词汇。"""
    ai = _make_unique_unit()
    # E2 前提:受控树先有这些知识点(模拟后台已定义),persist 才能命中并挂内容
    node_ids = await _seed_kp_nodes(db_session, [kp.name for kp in ai.knowledge_points])

    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()

    # 1. curriculum_units 找到这一行
    cu_found = (await db_session.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == cu.id)
    )).scalar_one()
    assert cu_found.unit_title == ai.unit_title

    # 2. unit_node 边挂到受控树节点(每个 KP 一条)。讲解不在 persist 时写(改由 admin 讲解补全 kp_lecture)。
    from app.models.d17_curriculum_kg import UnitNode
    edges = (await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id)
    )).scalars().all()
    assert len(edges) == len(ai.knowledge_points)
    assert {e.node_id for e in edges} == set(node_ids.values())

    # 5/6. curriculum_words ↔ vocabulary_words（>= 同理）
    cw = (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id)
    )).scalars().all()
    assert len(cw) >= len(ai.words)


@pytest.mark.asyncio
async def test_delete_units_cascades_associations_keeps_shared(db_session):
    """删除单元:连带删 知识图谱边(unit_node)+ 单词通词表(curriculum_words)+ 短文,
    但共享的 knowledge_nodes / vocabulary_words 主表保留。"""
    from app.models.d17_curriculum_kg import UnitNode
    from app.models.d4_knowledge import CurriculumUnitPassage, UnitPassageKp

    ai = _make_unique_unit()
    node_ids = await _seed_kp_nodes(db_session, [kp.name for kp in ai.knowledge_points])
    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()

    # 造一篇短文 + 短文↔考点边，验证级联删除短文链
    node_id_list = list(node_ids.values())
    passage = CurriculumUnitPassage(
        id=uuid.uuid4(), unit_id=cu.id, kind="阅读", title="T", text="body", sort_order=0)
    db_session.add(passage)
    await db_session.flush()
    db_session.add(UnitPassageKp(passage_id=passage.id, node_id=node_id_list[0]))
    await db_session.flush()

    # 记录被关联的 vocabulary_words id（应保留）
    word_ids = [w.word_id for w in (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id))).scalars().all()]
    assert word_ids

    n = await curriculum_service.delete_units(db_session, unit_ids=[cu.id])
    await db_session.flush()
    assert n == 1

    # 单元 + 所有关联均已删
    assert (await db_session.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == cu.id))).scalar_one_or_none() is None
    assert (await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id))).scalars().all() == []
    assert (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id))).scalars().all() == []
    assert (await db_session.execute(
        select(CurriculumUnitPassage).where(
            CurriculumUnitPassage.unit_id == cu.id))).scalars().all() == []
    assert (await db_session.execute(  # 短文删了 → 其考点边 DB 级联删
        select(UnitPassageKp).where(UnitPassageKp.passage_id == passage.id))).scalars().all() == []

    # 共享主表保留:知识节点 + 词汇
    from app.models.d15_knowledge_graph import KnowledgeNode
    assert (await db_session.execute(select(KnowledgeNode).where(
        KnowledgeNode.id.in_(node_id_list)))).scalars().all()
    assert (await db_session.execute(select(VocabularyWord).where(
        VocabularyWord.id.in_(word_ids)))).scalars().all()


@pytest.mark.asyncio
async def test_delete_units_ignores_unknown_ids(db_session):
    """传入不存在的 id：返回 0，不报错。"""
    n = await curriculum_service.delete_units(db_session, unit_ids=[uuid.uuid4()])
    assert n == 0


@pytest.mark.asyncio
async def test_persist_unit_unmatched_falls_to_candidate(db_session):
    """E2:树上无匹配节点时,persist_unit 不自建节点——落候选(供人工挂树),无 unit_node 边。
    讲解不再随生成暂存(旧 pending_kp_content 已退役),内容改由 admin 讲解补全生成。"""
    from app.models.d15_knowledge_graph import KpCandidate
    from app.models.d17_curriculum_kg import UnitNode
    from app.services.kp_normalize import normalize_kp_name
    ai = _make_unique_unit()                      # KP 名不在树上 → 全部未命中
    norms = [normalize_kp_name(kp.name) for kp in ai.knowledge_points]

    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()

    # 无 unit_node 边(未自建节点)
    edges = (await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id))).scalars().all()
    assert len(edges) == 0
    # 候选已建(供人工挂到树上)
    cand = (await db_session.execute(
        select(KpCandidate).where(KpCandidate.name_norm.in_(norms)))).scalars().all()
    assert len(cand) >= len(ai.knowledge_points)


@pytest.mark.asyncio
async def test_persist_unit_idempotent(db_session):
    """二次 persist 不应产生重复 unit_node 边（R8:KP 落图谱节点,单元知识点=unit_node 边）。"""
    from app.models.d17_curriculum_kg import UnitNode

    ai = _make_unique_unit()
    await _seed_kp_nodes(db_session, [kp.name for kp in ai.knowledge_points])

    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()
    count_1 = len((await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id))).scalars().all())

    cu2 = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()
    assert cu2.id == cu.id   # 同 code → 同单元,不新建
    count_2 = len((await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id))).scalars().all())

    assert count_1 == count_2 == len(ai.knowledge_points)


@pytest.mark.asyncio
async def test_unit_lock_first_unit_always_free(db_session):
    """unit_no=1 永远返回 locked=False，无论是否买学期。"""
    fake_user = uuid.uuid4()
    locked = await curriculum_service.is_unit_locked(
        db_session,
        user_id=fake_user,
        textbook_version="译林版", grade="小学5年级", semester="上",
        unit_no=1,
    )
    assert locked is False


@pytest.mark.asyncio
async def test_unit_lock_other_units_locked_without_semester(db_session):
    """unit_no>1 且无 PurchasedSemester 时 locked=True。"""
    fake_user = uuid.uuid4()
    locked = await curriculum_service.is_unit_locked(
        db_session,
        user_id=fake_user,
        textbook_version="译林版", grade="小学5年级", semester="上",
        unit_no=2,
    )
    assert locked is True
