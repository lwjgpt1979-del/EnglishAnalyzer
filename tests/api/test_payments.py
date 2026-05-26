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


# ── Membership Service Tests ───────────────────────────────────────────────────

from app.services.membership_service import activate_membership, get_active_membership


@pytest.mark.asyncio
async def test_get_active_membership_none_when_no_membership(db_session, test_user):
    result = await get_active_membership(db_session, user_id=test_user.id)
    assert result is None


@pytest.mark.asyncio
async def test_activate_new_membership(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    membership = await activate_membership(db_session, order=order)
    assert membership.tier == "basic"
    assert membership.is_active is True
    assert membership.user_id == test_user.id
    assert membership.order_id == order.id
    # expires_at should be roughly 1 month from now
    delta = membership.expires_at - datetime.now(timezone.utc)
    assert 25 <= delta.days <= 35  # 1 month ≈ 28-31 days


@pytest.mark.asyncio
async def test_renew_membership_extends_expiry(db_session, test_user):
    # First activation
    order1 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=1, order_type="new",
    )
    m1 = await activate_membership(db_session, order=order1)
    original_expires = m1.expires_at

    # Renew
    order2 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=3, order_type="renew",
    )
    m2 = await activate_membership(db_session, order=order2)

    # Same membership record (in-place update)
    assert m2.id == m1.id
    # expires_at extended by ~3 months
    delta = m2.expires_at - original_expires
    assert 85 <= delta.days <= 95  # 3 months ≈ 88-92 days


@pytest.mark.asyncio
async def test_upgrade_membership_deactivates_old(db_session, test_user):
    # Start with basic
    order1 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=1, order_type="new",
    )
    m1 = await activate_membership(db_session, order=order1)

    # Upgrade to pro
    order2 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="pro", duration_months=1, order_type="upgrade",
    )
    m2 = await activate_membership(db_session, order=order2)

    # Old membership deactivated
    await db_session.refresh(m1)
    assert m1.is_active is False
    # New membership is pro
    assert m2.tier == "pro"
    assert m2.is_active is True
    assert m2.id != m1.id


# ── WeChat Pay Service Tests ───────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.wechat_pay_service import (
    build_pay_params,
    verify_and_decrypt_callback,
)


def test_build_pay_params_returns_all_fields():
    """build_pay_params 应返回 wx.requestPayment 所需的 5 个字段。"""
    params = build_pay_params("wx_test_prepay_id_12345")
    assert "timeStamp" in params
    assert "nonceStr" in params
    assert params["package"] == "prepay_id=wx_test_prepay_id_12345"
    assert params["signType"] == "RSA"
    assert "paySign" in params
    # In dev mode (placeholder key), paySign is the dev placeholder
    assert len(params["paySign"]) > 0


def test_verify_and_decrypt_callback_dev_mode():
    """dev 模式：resource 含 mock_decrypted 时直接返回，无需真实解密。"""
    import json
    body = json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": "ORD-20260526-ABCD1234",
                "transaction_id": "4200002test",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    headers = {
        "wechatpay-timestamp": "1716739200",
        "wechatpay-nonce": "abc123",
        "wechatpay-signature": "dev_sig",
    }
    result = verify_and_decrypt_callback(headers, body)
    assert result["out_trade_no"] == "ORD-20260526-ABCD1234"
    assert result["trade_state"] == "SUCCESS"


@pytest.mark.asyncio
async def test_get_prepay_id_calls_wx_api(db_session, test_user):
    """get_prepay_id 应调用微信 API 并返回 prepay_id 字符串。"""
    from app.services.wechat_pay_service import get_prepay_id
    from app.services.order_service import create_order

    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_test_prepay_id_9999"}

    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)

        result = await get_prepay_id(order, openid="test_openid")

    assert result == "wx_test_prepay_id_9999"


# ── API Endpoint Tests ─────────────────────────────────────────────────────────

from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"pay_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_membership_returns_free_when_none(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/memberships/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["tier"] == "free"
    assert body["data"]["expires_at"] is None


@pytest.mark.asyncio
async def test_get_membership_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/memberships/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_order_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["tier"] == "basic"
    assert body["data"]["amount_fen"] == 2900
    assert body["data"]["status"] == "pending"
    assert body["data"]["order_no"].startswith("ORD-")


@pytest.mark.asyncio
async def test_create_order_invalid_tier(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "free", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_order_invalid_duration(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 6, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_order_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "pro", "duration_months": 3, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == order_id


@pytest.mark.asyncio
async def test_get_order_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(f"/api/v1/orders/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_order_invalid_order_type(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "gift"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pay_order_api(client: AsyncClient, auth_headers):
    """POST /orders/{id}/pay 应调用微信 API 并返回 PayParamsOut。"""
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_test_pay_12345"}

    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockHttpx:
        mock_instance = AsyncMock()
        MockHttpx.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockHttpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)

        resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["package"] == "prepay_id=wx_test_pay_12345"
    assert body["data"]["signType"] == "RSA"
    assert "timeStamp" in body["data"]


@pytest.mark.asyncio
async def test_pay_order_already_paid(client: AsyncClient, auth_headers):
    """已付款订单不能重复发起支付，应返回 400。"""
    import json as _json

    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]
    order_no = create_resp.json()["data"]["order_no"]

    # Simulate webhook marking the order as paid
    wx_callback = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": "4200002test999",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    await client.post(
        "/api/v1/webhooks/wx-pay",
        content=wx_callback,
        headers={
            "content-type": "application/json",
            "wechatpay-timestamp": "1716739200",
            "wechatpay-nonce": "testnonce",
            "wechatpay-signature": "dev",
        },
    )

    # Try to pay again
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_xxx"}
    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockHttpx:
        mock_instance = AsyncMock()
        MockHttpx.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockHttpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)
        resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wx_pay_webhook_activates_membership(client: AsyncClient, auth_headers):
    """微信回调成功后会员应被激活。"""
    import json as _json

    # Create order
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "pro", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_no = create_resp.json()["data"]["order_no"]

    # Simulate WeChat callback
    wx_callback = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": f"4200002wx{uuid.uuid4().hex[:8]}",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    cb_resp = await client.post(
        "/api/v1/webhooks/wx-pay",
        content=wx_callback,
        headers={
            "content-type": "application/json",
            "wechatpay-timestamp": "1716739200",
            "wechatpay-nonce": "testnonce",
            "wechatpay-signature": "dev",
        },
    )
    assert cb_resp.status_code == 200
    assert cb_resp.json() == {"code": "SUCCESS"}

    # Check membership
    membership_resp = await client.get("/api/v1/memberships/me", headers=auth_headers)
    assert membership_resp.json()["data"]["tier"] == "pro"


@pytest.mark.asyncio
async def test_wx_pay_webhook_idempotent(client: AsyncClient, auth_headers):
    """重复回调同一 wx_transaction_id 应幂等（返回 SUCCESS，不报错）。"""
    import json as _json

    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_no = create_resp.json()["data"]["order_no"]
    wx_tid = f"4200002idem{uuid.uuid4().hex[:6]}"

    payload = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": wx_tid,
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    headers_cb = {
        "content-type": "application/json",
        "wechatpay-timestamp": "1716739200",
        "wechatpay-nonce": "testnonce",
        "wechatpay-signature": "dev",
    }

    resp1 = await client.post("/api/v1/webhooks/wx-pay", content=payload, headers=headers_cb)
    resp2 = await client.post("/api/v1/webhooks/wx-pay", content=payload, headers=headers_cb)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == {"code": "SUCCESS"}
    assert resp2.json() == {"code": "SUCCESS"}
