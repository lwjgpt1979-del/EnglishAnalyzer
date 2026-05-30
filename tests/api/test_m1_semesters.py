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
