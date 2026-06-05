"""seed_yilin.seed_grade 集成测试（TDD / dev mock）。"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit, UnitKnowledgePoint


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时调到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_seed_grade_creates_units(db_session):
    """seed_grade 小学5年级 2单元/学期 → DB 里该年级单元数 >= 4。"""
    from scripts.seed_yilin import seed_grade

    await seed_grade(
        db_session,
        textbook_version="译林版",
        grade="小学5年级",
        units_per_semester=2,
    )
    await db_session.flush()

    count = (await db_session.execute(
        select(func.count()).select_from(CurriculumUnit).where(
            CurriculumUnit.textbook_version == "译林版",
            CurriculumUnit.grade == "小学5年级",
        )
    )).scalar_one()
    assert count >= 4, f"期望 >= 4 个单元，实际 {count}"


@pytest.mark.asyncio
async def test_seed_grade_units_have_knowledge_points(db_session):
    """每个种子单元下至少有 3 个知识点。"""
    from scripts.seed_yilin import seed_grade

    await seed_grade(
        db_session,
        textbook_version="译林版",
        grade="小学5年级",
        units_per_semester=2,
    )
    await db_session.flush()

    units = (await db_session.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == "译林版",
            CurriculumUnit.grade == "小学5年级",
        )
    )).scalars().all()

    for unit in units:
        kp_count = (await db_session.execute(
            select(func.count()).select_from(UnitKnowledgePoint).where(
                UnitKnowledgePoint.unit_id == unit.id
            )
        )).scalar_one()
        assert kp_count >= 3, (
            f"单元 {unit.unit_no} ({unit.semester}) 只有 {kp_count} 个知识点，期望 >= 3"
        )


@pytest.mark.asyncio
async def test_seed_grade_idempotent(db_session):
    """幂等：二次 seed_grade 单元数不翻倍。"""
    from scripts.seed_yilin import seed_grade

    await seed_grade(
        db_session,
        textbook_version="译林版",
        grade="小学5年级",
        units_per_semester=2,
    )
    await db_session.flush()

    count_first = (await db_session.execute(
        select(func.count()).select_from(CurriculumUnit).where(
            CurriculumUnit.textbook_version == "译林版",
            CurriculumUnit.grade == "小学5年级",
        )
    )).scalar_one()

    await seed_grade(
        db_session,
        textbook_version="译林版",
        grade="小学5年级",
        units_per_semester=2,
    )
    await db_session.flush()

    count_second = (await db_session.execute(
        select(func.count()).select_from(CurriculumUnit).where(
            CurriculumUnit.textbook_version == "译林版",
            CurriculumUnit.grade == "小学5年级",
        )
    )).scalar_one()

    assert count_second == count_first, (
        f"幂等失败：第一次 {count_first}，第二次 {count_second}"
    )
