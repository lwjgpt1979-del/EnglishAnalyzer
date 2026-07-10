"""seed_yilin.seed_grade 集成测试（TDD / dev mock）。"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit  # R8:UnitKnowledgePoint 已退役,单元知识点=unit_node 边


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时调到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


async def _seed_tree_for_units(db, unit_nos, *, textbook="译林版", grade="小学5年级"):
    """E2:受控树先有 mock 各单元的知识点名,seed_grade 才能映射建边。
    用 generate_unit 取 mock 名(确定性,仅依赖 unit_no),在本 session 建节点+别名。"""
    import uuid
    from app.services import curriculum_ai_service as ais
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.services.kp_normalize import normalize_kp_name
    seen = set()
    for uno in unit_nos:
        ai = await ais.generate_unit(textbook_version=textbook, grade=grade, semester="上", unit_no=uno)
        for kp in ai.knowledge_points:
            norm = normalize_kp_name(kp.name)
            if norm in seen:
                continue
            seen.add(norm)
            nid = uuid.uuid4()
            db.add(KnowledgeNode(id=nid, axis="knowledge", name=kp.name,
                                 code=f"ttree-{uuid.uuid4().hex[:8]}", status="active", source="seed"))
            await db.flush()
            db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=kp.name,
                             alias_norm=norm, source="seed"))
            await db.flush()


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
    """E2:受控树有匹配节点时,每个种子单元映射出 >= 3 条 unit_node 边。"""
    from scripts.seed_yilin import seed_grade

    # E2 前提:树先有 mock 单元(1,2)的知识点名
    await _seed_tree_for_units(db_session, [1, 2])
    await seed_grade(
        db_session,
        textbook_version="译林版",
        grade="小学5年级",
        units_per_semester=2,
    )
    await db_session.flush()

    # 仅校验本次 seed 建的单元(unit_no≤2);库里可能有历史提交的更高 unit_no(旧数据无 unit_node)
    units = (await db_session.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == "译林版",
            CurriculumUnit.grade == "小学5年级",
            CurriculumUnit.unit_no <= 2,
        )
    )).scalars().all()

    from app.models.d17_curriculum_kg import UnitNode
    for unit in units:
        kp_count = (await db_session.execute(
            select(func.count()).select_from(UnitNode).where(
                UnitNode.unit_id == unit.id   # R8.4:单元知识点 = unit_node 边
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
