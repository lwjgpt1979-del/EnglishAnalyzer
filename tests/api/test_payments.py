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
