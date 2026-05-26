from app.core.config import settings


def test_settings_has_wechat_pay_config():
    """Settings 必须有微信支付必要字段。"""
    assert hasattr(settings, "wechat_pay_mch_id")
    assert hasattr(settings, "wechat_pay_api_key_v3")
    assert hasattr(settings, "wechat_pay_cert_serial")
    assert hasattr(settings, "wechat_pay_private_key_pem")
    assert hasattr(settings, "wechat_pay_notify_url")
    assert hasattr(settings, "wechat_pay_skip_sig_verify")
    assert isinstance(settings.wechat_pay_skip_sig_verify, bool)


import uuid
from datetime import datetime, timezone

from app.schemas.payments import (
    CurrentMembershipOut,
    OrderCreate,
    OrderOut,
    PayParamsOut,
)


def test_current_membership_out_defaults_to_free():
    """无会员时，默认 tier=free，expires_at=None。"""
    out = CurrentMembershipOut()
    assert out.tier == "free"
    assert out.expires_at is None
    assert out.is_active is True


def test_current_membership_out_with_paid_tier():
    now = datetime.now(timezone.utc)
    out = CurrentMembershipOut(
        tier="pro",
        started_at=now,
        expires_at=now,
        is_active=True,
    )
    assert out.tier == "pro"


def test_order_create_validates_fields():
    order = OrderCreate(tier="basic", duration_months=3, order_type="new")
    assert order.tier == "basic"
    assert order.duration_months == 3


def test_order_out_serializes():
    now = datetime.now(timezone.utc)
    out = OrderOut(
        id=uuid.uuid4(),
        order_no="ORD-20260526-ABCD1234",
        tier="pro",
        duration_months=1,
        amount_fen=4900,
        status="pending",
        wx_transaction_id=None,
        paid_at=None,
        created_at=now,
    )
    assert out.amount_fen == 4900
    assert out.status == "pending"


def test_pay_params_out_has_required_fields():
    params = PayParamsOut(
        timeStamp="1716739200",
        nonceStr="abc123",
        package="prepay_id=wx12345",
        signType="RSA",
        paySign="base64sighere",
    )
    assert params.signType == "RSA"


# ── Order Service Tests ────────────────────────────────────────────────────────

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services.order_service import (
    PRICE_TABLE,
    create_order,
    get_order,
    get_price,
    mark_order_paid,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    from app.services.auth_service import upsert_user
    user = await upsert_user(db_session, openid=f"pay_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


def test_price_table_has_all_tiers():
    assert set(PRICE_TABLE.keys()) == {"basic", "pro", "promax"}
    for tier in PRICE_TABLE:
        assert set(PRICE_TABLE[tier].keys()) == {1, 3, 12}


def test_get_price_returns_fen():
    assert get_price("basic", 1) == 2900
    assert get_price("pro", 3) == 13800
    assert get_price("promax", 12) == 98800


def test_get_price_invalid_tier_raises():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc_info:
        get_price("free", 1)
    assert exc_info.value.code == 400


def test_get_price_invalid_duration_raises():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc_info:
        get_price("basic", 6)
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_create_order(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    assert order.id is not None
    assert order.order_no.startswith("ORD-")
    assert order.amount_fen == 2900
    assert order.status == "pending"
    assert order.tier == "basic"


@pytest.mark.asyncio
async def test_get_order_by_payer(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="pro",
        duration_months=3,
        order_type="new",
    )
    found = await get_order(db_session, order_id=order.id, user_id=test_user.id)
    assert found is not None
    assert found.id == order.id


@pytest.mark.asyncio
async def test_get_order_wrong_user_returns_none(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    found = await get_order(db_session, order_id=order.id, user_id=uuid.uuid4())
    assert found is None


@pytest.mark.asyncio
async def test_mark_order_paid(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    updated = await mark_order_paid(
        db_session, order=order, wx_transaction_id="4200002test"
    )
    assert updated.status == "paid"
    assert updated.wx_transaction_id == "4200002test"
    assert updated.paid_at is not None
