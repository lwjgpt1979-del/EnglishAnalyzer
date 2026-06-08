"""Admin 课程内容生成端点 TDD 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def seeded_unit_id(db: AsyncSession) -> str:
    """植入一个最小课程单元用于生成测试（幂等：先删旧行）。"""
    from sqlalchemy import delete
    from app.models.d4_knowledge import CurriculumUnit as CU
    # unit_no must be ≤ 20 (AIGeneratedUnit schema cap); use 18 to avoid clash with other tests
    # Cascade delete all FK-dependent rows before deleting the unit
    from sqlalchemy import text
    cleanup_sql = """
    DO $$
    DECLARE _ids UUID[];
    BEGIN
      SELECT ARRAY(SELECT id FROM curriculum_units
                   WHERE textbook_version='译林版' AND grade='小学5年级'
                     AND semester='上' AND unit_no=18)
      INTO _ids;
      DELETE FROM unit_knowledge_points WHERE unit_id = ANY(_ids);
      DELETE FROM curriculum_words WHERE unit_id = ANY(_ids);
      DELETE FROM curriculum_units WHERE id = ANY(_ids);
    END $$;
    """
    await db.execute(text(cleanup_sql))
    await db.commit()
    unit = CurriculumUnit(
        id=uuid.uuid4(),
        textbook_version="译林版",
        grade="小学5年级",
        semester="上",
        unit_no=18,
        unit_title="Test Unit",
    )
    db.add(unit)
    await db.flush()
    await db.commit()
    return str(unit.id)


# ── 鉴权检查 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_units_requires_admin(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generate_requires_admin(client: AsyncClient):
    """非 admin 调用生成 → 401。"""
    r = await client.post(f"/api/v1/admin/curriculum/units/{uuid.uuid4()}/generate")
    assert r.status_code == 401


# ── 正常流程 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_curriculum_units_returns_list(admin_client: AsyncClient):
    """Admin 鉴权 → 200 + list（允许为空）。"""
    r = await admin_client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_curriculum_units_has_correct_fields(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """返回的每条数据有 unit_id / kp_count / content_count / content_rate 字段。"""
    r = await admin_client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 200
    items = r.json()["data"]
    # 找到刚植入的单元
    target = next((i for i in items if i["unit_id"] == seeded_unit_id), None)
    assert target is not None
    assert "kp_count" in target
    assert "content_count" in target
    assert "content_rate" in target


@pytest.mark.asyncio
async def test_generate_unit_content_success(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """有效 unit_id → 200 + content_count > 0（dev mock 生成）。"""
    r = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["unit_id"] == seeded_unit_id
    assert data["kp_count"] > 0
    assert data["content_count"] > 0
    assert 0.0 <= data["content_rate"] <= 1.0


@pytest.mark.asyncio
async def test_generate_unit_invalid_id(admin_client: AsyncClient):
    """不存在的 unit_id → 404。"""
    r = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{uuid.uuid4()}/generate"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_unit_is_idempotent(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """重复生成同一单元不会报错（persist_unit 幂等）。"""
    r1 = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    r2 = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
