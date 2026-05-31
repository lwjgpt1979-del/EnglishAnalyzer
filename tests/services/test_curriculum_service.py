"""curriculum_service.persist_unit 幂等性 + paywall 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d4_knowledge import (
    CurriculumUnit,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.models.d11_v2_curriculum import KnowledgePointContent
from app.services import curriculum_ai_service, curriculum_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_persist_unit_creates_all_6_tables(db_session):
    """persist_unit 一次性写入 6 张表（针对本次单元 + 知识点的行）。"""
    ai = await curriculum_ai_service.generate_unit(
        textbook_version="译林版", grade="小学5年级", semester="上", unit_no=1,
    )

    cu = await curriculum_service.persist_unit(db_session, ai_unit=ai)
    await db_session.flush()

    # 1. curriculum_units 找到这一行
    cu_found = (await db_session.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == cu.id)
    )).scalar_one()
    assert cu_found.unit_title == ai.unit_title

    # 2/3. unit_knowledge_points 链接到本单元
    links = (await db_session.execute(
        select(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id == cu.id)
    )).scalars().all()
    assert len(links) == len(ai.knowledge_points)

    # knowledge_points 至少有本次 AI 输出的全部（按 code 查）
    codes = [kp.code for kp in ai.knowledge_points]
    found_kps = (await db_session.execute(
        select(KnowledgePoint).where(KnowledgePoint.code.in_(codes))
    )).scalars().all()
    assert len(found_kps) == len(codes)

    # 4. knowledge_point_contents：每个 KP × 4 维度
    kp_ids = [kp.id for kp in found_kps]
    contents = (await db_session.execute(
        select(KnowledgePointContent).where(
            KnowledgePointContent.knowledge_point_id.in_(kp_ids)
        )
    )).scalars().all()
    assert len(contents) == len(kp_ids) * 4

    # 5/6. curriculum_words ↔ vocabulary_words
    cw = (await db_session.execute(
        select(CurriculumWord).where(CurriculumWord.unit_id == cu.id)
    )).scalars().all()
    assert len(cw) == len(ai.words)


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
