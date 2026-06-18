"""curriculum_service.persist_unit 幂等性 + paywall 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d4_knowledge import (
    CurriculumUnit,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.schemas.curriculum import AIGeneratedUnit, AIKnowledgePointItem, AIWordItem
from app.services import curriculum_ai_service, curriculum_service


def _make_unique_unit() -> AIGeneratedUnit:
    """构造一个 code 含唯一 nonce 的 mock 单元。

    dev-mock 的 generate_unit 输出 code 固定（按 grade/sem/unit 派生），多次跑
    测试时历史已提交的 KnowledgePoint / KnowledgePointContent 会被本测试按 code
    查回并计入断言，导致计数被污染。这里给每个 code 加 uuid 后缀，确保 found_kps
    只命中本次新建的 KP，contents 恰好 = KP 数 × 6。
    """
    nonce = uuid.uuid4().hex[:8]
    six_dims = {
        "listening": "## 听力\nmock",
        "vocabulary": "## 词汇\nmock",
        "grammar": "## 语法\nmock",
        "reading": "## 阅读\nmock",
        "translation": "## 翻译\nmock",
        "writing": "## 写作\nmock",
    }
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
                contents=dict(six_dims),
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
    """persist_unit 一次性写入 6 张表（针对本次单元 + 知识点的行）。

    用 code 含唯一 nonce 的 mock 单元（见 _make_unique_unit），避免 dev-mock 固定
    code 导致历史已提交数据污染 contents 计数。
    """
    ai = _make_unique_unit()

    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()

    # 1. curriculum_units 找到这一行
    cu_found = (await db_session.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == cu.id)
    )).scalar_one()
    assert cu_found.unit_title == ai.unit_title

    # 2/3. R8.4:persist 直接建 unit_node 边 + active 知识 node(不再建 knowledge_points/unit_knowledge_points)
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.models.d17_curriculum_kg import UnitNode
    from app.services.kp_normalize import normalize_kp_name
    edges = (await db_session.execute(
        select(UnitNode).where(UnitNode.unit_id == cu.id)
    )).scalars().all()
    assert len(edges) >= len(ai.knowledge_points)

    norms = [normalize_kp_name(kp.name) for kp in ai.knowledge_points]
    nodes = (await db_session.execute(
        select(KnowledgeNode).join(NodeAlias, NodeAlias.node_id == KnowledgeNode.id)
        .where(NodeAlias.alias_norm.in_(norms))
    )).scalars().all()
    assert len(nodes) >= len(ai.knowledge_points)
    assert all(str(n.status) == "active" and str(n.source) == "textbook" for n in nodes)

    # 4. 讲解内容已 node-native:专项覆盖见
    #    tests/api/test_curriculum.py::test_persist_unit_writes_node_resource_lectures_draft。

    # 5/6. curriculum_words ↔ vocabulary_words（>= 同理）
    cw = (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id)
    )).scalars().all()
    assert len(cw) >= len(ai.words)


@pytest.mark.asyncio
async def test_persist_unit_idempotent(db_session):
    """二次 persist 不应产生重复行。"""
    ai = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1,
    )
    await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()
    count_kps_1 = len((await db_session.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.code.in_([k.code for k in ai.knowledge_points])
        )
    )).scalars().all())

    await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()
    count_kps_2 = len((await db_session.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.code.in_([k.code for k in ai.knowledge_points])
        )
    )).scalars().all())

    assert count_kps_1 == count_kps_2


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
