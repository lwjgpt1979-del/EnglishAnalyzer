from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── 会员 ─────────────────────────────────────────────────────────────────────


class CurrentMembershipOut(BaseModel):
    """GET /memberships/me 响应体。

    无付费会员时 tier="free"，其余字段为 None。
    """

    tier: str = Field(default="free", description="free | basic | pro | promax")
    started_at: datetime | None = None
    expires_at: datetime | None = Field(
        default=None, description="到期时间；free 档永不过期，值为 None"
    )
    is_active: bool = True

    model_config = {"from_attributes": True}


# ── 订单 ─────────────────────────────────────────────────────────────────────


class OrderCreate(BaseModel):
    """POST /orders/ 请求体。"""

    tier: str = Field(..., description="basic | pro | promax")
    duration_months: int = Field(..., description="1 | 3 | 12")
    order_type: str = Field(..., description="new | renew | upgrade")


class OrderOut(BaseModel):
    """订单响应体。"""

    id: uuid.UUID
    order_no: str
    tier: str
    duration_months: int
    amount_fen: int = Field(..., description="实收金额（分）")
    status: str = Field(..., description="pending | paid | refunded | partial_refunded")
    wx_transaction_id: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 支付参数 ──────────────────────────────────────────────────────────────────


class PayParamsOut(BaseModel):
    """POST /orders/{id}/pay 响应体，前端传给 wx.requestPayment()。"""

    timeStamp: str
    nonceStr: str
    package: str = Field(..., description="prepay_id=wx...")
    signType: str = Field(default="RSA")
    paySign: str
