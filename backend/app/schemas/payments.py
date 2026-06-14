from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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
    """POST /orders/ 请求体。V1（duration_months）和 V2（semesters）双模式。"""

    tier: str = Field(..., description="basic | pro | promax")
    duration_months: int | None = Field(None, description="遗留按月：1 | 3 | 12（激活码等）")
    quantity: int | None = Field(None, description="按份：每份6个月，x份=6x月（优先于 duration_months）")
    addon_feature_key: str | None = Field(None, description="加量包：购买某功能的加量次数")
    order_type: str = Field(..., description="new | renew | upgrade")
    minor_consent: bool = Field(default=False, description="14-17岁用户首次购买必须为 True（已告知监护人并获得同意）")
    target_student_id: uuid.UUID | None = Field(None, description="代付时指定学生 ID；为空则为本人购买")
    # V2 学期会员（D-079）。非空 → V2 计价；空则 V1 旧 duration_months
    semesters: list[dict] | None = Field(None, description="V2：[{textbook_version,grade,semester}]")


class OrderOut(BaseModel):
    """订单响应体。"""

    id: uuid.UUID
    order_no: str
    tier: str
    duration_months: int
    amount_fen: int = Field(..., description="实收金额（分）")
    amount: int = Field(0, description="实收金额（元）— amount_fen / 100，方便前端展示")
    status: str = Field(..., description="pending | paid | refunded | partial_refunded")
    wx_transaction_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _fill_amount(self) -> "OrderOut":
        if self.amount == 0 and self.amount_fen:
            self.amount = self.amount_fen // 100
        return self


# ── 支付参数 ──────────────────────────────────────────────────────────────────


class PayParamsOut(BaseModel):
    """POST /orders/{id}/pay 响应体，前端传给 wx.requestPayment()。"""

    timeStamp: str
    nonceStr: str
    package: str = Field(..., description="prepay_id=wx...")
    signType: str = Field(default="RSA")
    paySign: str
