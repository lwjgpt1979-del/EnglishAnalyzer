"""curriculum API 端点集成测试（D-079 / M2）。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import _async_session_factory
from app.main import app
from app.services import curriculum_ai_service, curriculum_service


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时 _seed_unit 打到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


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


async def _seed_unit(unit_no: int = 19) -> None:
    """Seed one curriculum unit with its own DB session (committed).

    Uses unit_no in 19..20 to avoid colliding with production seed data
    (which uses 1..8 per semester) while staying within the AIGeneratedUnit
    schema cap (unit_no <= 20). KP codes are tied to (grade_short,
    sem_short, unit_no) so a high unit_no guarantees code uniqueness.
    The API request will open a separate DB session, so commit is needed.
    """
    async with _async_session_factory() as s:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="小学5年级", semester="上",
            unit_no=unit_no,
        )
        await curriculum_service.persist_unit(s, ai_unit=ai)
        await s.commit()


async def _seed_user_with_semester(openid: str) -> uuid.UUID:
    """Create a user + grant them a PurchasedSemester for 译林版/小学5年级/上.
    Returns the user_id. Used by tests that need an unlocked unit.

    NB: PurchasedSemester.order_id is NOT NULL FK → we create a paid Order first.
    """
    from datetime import datetime, timezone
    from app.services.auth_service import upsert_user
    from app.models.d2_payments import Order
    async with _async_session_factory() as s:
        user = await upsert_user(s, openid=openid)
        await s.flush()
        order = Order(
            id=uuid.uuid4(),
            order_no=f"TEST-{uuid.uuid4().hex[:8]}",
            payer_id=user.id,
            beneficiary_id=user.id,
            order_type="new",
            tier="pro",
            duration_months=6,
            amount_fen=7900,
            status="paid",
            paid_at=datetime.now(timezone.utc),
            semester_count=1,
        )
        s.add(order)
        await s.flush()
        from app.services.semester_service import create_purchased_semesters
        await create_purchased_semesters(
            s,
            user_id=user.id,
            tier="pro",
            semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
            order_id=order.id,
        )
        await s.commit()
        return user.id


@pytest.mark.asyncio
async def test_list_units_returns_locked_field(client):
    """GET /curriculum/units 必须返回 locked 字段；非购买用户对 unit_no>=19 都 locked=true。
    (unit_no=1 永久免费的逻辑在 test_curriculum_service.py 单测里覆盖。)"""
    await _seed_unit(19)
    await _seed_unit(20)

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
    u19 = next(u for u in units if u["unit_no"] == 19)
    u20 = next(u for u in units if u["unit_no"] == 20)
    # 该 test 用户未购学期，u19/u20 都应 locked
    assert u19["locked"] is True
    assert u20["locked"] is True
    assert u19["kp_count"] >= 3


@pytest.mark.asyncio
async def test_get_unit_detail_403_when_locked(client):
    """unit_no=19 详情对无学期用户返回 403。"""
    await _seed_unit(19)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 19,
            )
        )).scalar_one()
        unit_id = cu.id

    h = await _login(client, f"detail403_{uuid.uuid4().hex[:6]}")
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_unit_detail_200_for_owned_semester(client):
    """购买了 (译林版,小学5年级,上) 学期的用户访问 unit_no=19 详情应 200，不受 unit_no>1 锁限制。"""
    await _seed_unit(19)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 19,
            )
        )).scalar_one()
        unit_id = cu.id

    # 让本测试用户拥有该学期
    suffix = f"d200_{uuid.uuid4().hex[:6]}"
    await _seed_user_with_semester(f"m2_curriculum_{suffix}")

    h = await _login(client, suffix)
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["unit_no"] == 19
    assert detail["locked"] is False
    assert len(detail["knowledge_points"]) >= 3
    assert len(detail["words"]) >= 5


@pytest.mark.asyncio
async def test_get_kp_contents_returns_4_dimensions(client):
    """GET /knowledge-points/{id}/contents 返回 4 维度内容，每条带 dimension/content_md。
    KP 所属 unit_no=19 受 paywall，所以测试用户需先有学期。"""
    await _seed_unit(19)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit, UnitKnowledgePoint
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 19,
            )
        )).scalar_one()
        link = (await s.execute(
            select(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id == cu.id)
        )).scalars().first()
        kp_id = link.knowledge_point_id

    suffix = f"kpcontent_{uuid.uuid4().hex[:6]}"
    await _seed_user_with_semester(f"m2_curriculum_{suffix}")

    h = await _login(client, suffix)
    resp = await client.get(
        f"/api/v1/curriculum/knowledge-points/{kp_id}/contents",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    contents = resp.json()["data"]
    assert len(contents) == 4
    dims = {c["dimension"] for c in contents}
    assert dims == {"listening", "dictation", "grammar", "writing"}
    for c in contents:
        assert c["content_md"]
        assert "audio_url" in c
