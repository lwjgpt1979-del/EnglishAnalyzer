"""curriculum API 端点集成测试（D-079 / M2）。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.services import curriculum_ai_service, curriculum_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"m2_curriculum_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_unit(unit_no: int) -> None:
    """Seed one curriculum unit with its own DB session (committed, not rolled back).

    The API request will open a separate DB session, so we must commit here.
    """
    async with _async_session_factory() as s:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="小学5年级", semester="上",
            unit_no=unit_no,
        )
        await curriculum_service.persist_unit(s, ai_unit=ai)
        await s.commit()


@pytest.mark.asyncio
async def test_list_units_returns_locked_field(client):
    """GET /curriculum/units 必须返回 locked 字段，unit_no=1 永远 false。"""
    await _seed_unit(1)
    await _seed_unit(2)

    h = await _login(client, f"list_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        "/api/v1/curriculum/units",
        params={"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    units = body["data"]
    assert len(units) >= 2

    u1 = next(u for u in units if u["unit_no"] == 1)
    u2 = next(u for u in units if u["unit_no"] == 2)
    assert u1["locked"] is False
    assert u2["locked"] is True
    assert u1["kp_count"] >= 3


@pytest.mark.asyncio
async def test_get_unit_detail_403_when_locked(client):
    """unit_no=2 详情对无学期用户返回 403。"""
    await _seed_unit(2)

    # Look up the seeded unit id via a fresh session
    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 2,
            )
        )).scalar_one()
        unit_id = cu.id

    h = await _login(client, f"detail403_{uuid.uuid4().hex[:6]}")
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_unit_detail_200_for_unit_1(client):
    """unit_no=1 详情免费打开，返回 KP 列表 + 词汇列表。"""
    await _seed_unit(1)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 1,
            )
        )).scalar_one()
        unit_id = cu.id

    h = await _login(client, f"detail200_{uuid.uuid4().hex[:6]}")
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["unit_no"] == 1
    assert detail["locked"] is False
    assert len(detail["knowledge_points"]) >= 3
    assert len(detail["words"]) >= 5
