"""M1 学期会员测试（D-079）。"""
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services.auth_service import upsert_user
from app.services.pricing_service import (
    get_semester_pricing, calc_total_fen, DEFAULT_PRICING,
)
from app.services.semester_service import (
    create_purchased_semesters, query_access, assert_can_access,
    SEMESTER_DURATION_DAYS,
)
from app.core.exceptions import AppError


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student(db_session):
    u = await upsert_user(db_session, openid=f"m1_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_pricing_from_config_or_default(db_session):
    p = await get_semester_pricing(db_session)
    # 迁移 0008 已 seed，或返回 DEFAULT；两种都接受
    assert p.basic in (39, DEFAULT_PRICING.basic)
    assert p.pro in (79, DEFAULT_PRICING.pro)
    assert p.promax in (159, DEFAULT_PRICING.promax)


def test_calc_total_fen():
    p = DEFAULT_PRICING
    assert calc_total_fen(p, tier="basic", semester_count=1) == 3900
    assert calc_total_fen(p, tier="pro", semester_count=2) == 79 * 2 * 100
    assert calc_total_fen(p, tier="promax", semester_count=3) == 159 * 3 * 100


@pytest.mark.asyncio
async def test_create_and_query_access(db_session, student):
    fake_order_id = uuid.uuid4()
    from app.models.d2_payments import Order
    db_session.add(Order(
        id=fake_order_id, order_no=f"TEST-{uuid.uuid4().hex[:8]}",
        payer_id=student.id, beneficiary_id=student.id,
        order_type="new", tier="basic", duration_months=6, amount_fen=3900,
        status="paid",
    ))
    await db_session.flush()

    ps_list = await create_purchased_semesters(
        db_session, user_id=student.id, tier="basic",
        semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
        order_id=fake_order_id,
    )
    assert len(ps_list) == 1
    ps = ps_list[0]
    assert ps.semester_no == 1
    assert (ps.expires_at - ps.started_at).days == SEMESTER_DURATION_DAYS

    ok, tier, _ = await query_access(
        db_session, user_id=student.id,
        textbook_version="译林版", grade="小学5年级", semester="上",
    )
    assert ok is True
    assert tier == "basic"


@pytest.mark.asyncio
async def test_query_access_no_purchase(db_session, student):
    ok, tier, _ = await query_access(
        db_session, user_id=student.id,
        textbook_version="译林版", grade="小学5年级", semester="上",
    )
    assert ok is False
    assert tier is None


@pytest.mark.asyncio
async def test_assert_can_access_403_no_purchase(db_session, student):
    with pytest.raises(AppError) as exc:
        await assert_can_access(
            db_session, user_id=student.id,
            textbook_version="译林版", grade="小学5年级", semester="上",
        )
    assert exc.value.code == 403


@pytest.mark.asyncio
async def test_assert_can_access_403_tier_too_low(db_session, student):
    """basic 用户访问 pro 内容应 403。"""
    fake_order_id = uuid.uuid4()
    from app.models.d2_payments import Order
    db_session.add(Order(
        id=fake_order_id, order_no=f"TEST-{uuid.uuid4().hex[:8]}",
        payer_id=student.id, beneficiary_id=student.id,
        order_type="new", tier="basic", duration_months=6, amount_fen=3900,
        status="paid",
    ))
    await db_session.flush()
    await create_purchased_semesters(
        db_session, user_id=student.id, tier="basic",
        semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
        order_id=fake_order_id,
    )

    with pytest.raises(AppError) as exc:
        await assert_can_access(
            db_session, user_id=student.id,
            textbook_version="译林版", grade="小学5年级", semester="上",
            required_tier="pro",
        )
    assert exc.value.code == 403


# ── API 测试 ──────────────────────────────────────────────────────────────────
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, suffix):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"m1_api_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_complete_profile_with_textbook_preference(client):
    h = await _login(client, f"pref_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/auth/complete-profile",
        json={
            "birth_year": 1990, "agreement_version": "v1.0",
            "preferred_textbook_version": "译林版",
            "preferred_grade": "小学5年级",
            "preferred_semester": "上",
        }, headers=h,
    )
    assert r.status_code == 200
    # 验证字段写入数据库
    from app.core.database import _async_session_factory
    from sqlalchemy import select
    from app.models.d1_users import User
    async with _async_session_factory() as s:
        user = (await s.execute(
            select(User).where(User.openid.like("m1_api_pref_%"))
            .order_by(User.created_at.desc()).limit(1)
        )).scalar_one()
        assert user.preferred_textbook_version == "译林版"
        assert user.preferred_grade == "小学5年级"
        assert str(user.preferred_semester) == "上"


@pytest.mark.asyncio
async def test_v2_order_creation_calculates_correct_amount(client):
    """V2 下单（指定 semesters）金额 = tier×单价×数量"""
    h = await _login(client, f"order_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=h,
    )
    r = await client.post(
        "/api/v1/orders/",
        json={
            "tier": "pro",
            "order_type": "new",
            "semesters": [
                {"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"},
                {"textbook_version": "译林版", "grade": "小学5年级", "semester": "下"},
            ],
        }, headers=h,
    )
    # 79 * 2 * 100 = 15800
    assert r.status_code == 200, r.text
    assert r.json()["data"]["amount_fen"] == 15800


@pytest.mark.asyncio
async def test_semesters_mine_endpoint_empty(client):
    """新用户调 /semesters/mine 返回空 list。"""
    h = await _login(client, f"sm_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=h,
    )
    r = await client.get("/api/v1/semesters/mine", headers=h)
    assert r.status_code == 200
    assert r.json()["data"] == []
