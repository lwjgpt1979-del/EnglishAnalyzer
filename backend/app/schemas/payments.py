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
    payment_confirm_log_id: uuid.UUID | None = Field(
        None, description="支付确认留存记录 ID（§4.6，下单前 payment-confirm 返回）"
    )
    is_promotional: bool = Field(default=False, description="是否活动价订单（活动价不支持退款）")


class OrderOut(BaseModel):
    """订单响应体。"""

    id: uuid.UUID
    order_no: str
    tier: str
    duration_months: int
    amount_fen: int = Field(..., description="实收金额（分）")
    amount: int = Field(0, description="实收金额（元）— amount_fen / 100，方便前端展示")
    status: str = Field(..., description="pending | paid | refunded | partial_refunded")
    refund_status: str = Field("NONE", description="退款状态码（§4.5.2）")
    appeal_status: str = Field("NONE", description="申诉状态码（§4.5.2）")
    wx_transaction_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _fill_amount(self) -> "OrderOut":
        if self.amount == 0 and self.amount_fen:
            self.amount = self.amount_fen // 100
        return self


# ── 退款 / 申诉（§4.5）──────────────────────────────────────────────────────────


class PaymentConfirmCreate(BaseModel):
    """POST /orders/payment-confirm 请求体（§4.6.3）。

    服务端补全 confirmed_at / ip_address / user_agent；客户端不得传这些。
    两个勾选缺一不可。
    """

    plan_snapshot: dict | None = Field(None, description="当时展示的套餐信息快照")
    checkbox_refund_policy: bool = Field(..., description="勾选退款规则确认框")
    checkbox_digital_service: bool = Field(..., description="勾选虚拟数字服务确认框")
    device_id: str | None = None
    session_id: str | None = None


class PaymentConfirmOut(BaseModel):
    log_id: uuid.UUID

    model_config = {"from_attributes": True}


class AppealCreate(BaseModel):
    """POST /orders/{id}/appeal 请求体（超7天有理由申诉）。"""

    appeal_type: str = Field(
        ..., description="SYSTEM_FAULT | DESC_MISMATCH | DUPLICATE_PURCHASE | MINOR_PURCHASE"
    )
    note: str | None = Field(None, description="申诉说明")
    evidence_urls: list[str] | None = Field(None, description="证明截图 URL 列表")


class RefundOut(BaseModel):
    """退款 / 申诉处理结果。"""

    id: uuid.UUID
    order_id: uuid.UUID
    amount_fen: int
    refund_type: str
    status: str = Field(..., description="pending | approved | rejected | completed")
    state_code: str | None = None
    appeal_type: str | None = None
    wx_refund_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 后台审核（P3）────────────────────────────────────────────────────────────


class AdminRefundItem(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_no: str
    kind: str = Field(..., description="refund | appeal")
    refund_type: str
    appeal_type: str | None = None
    state_code: str | None = None
    status: str
    amount_fen: int = Field(..., description="退款金额（分）")
    order_amount_fen: int = Field(..., description="订单实付金额（分）")
    reason: str | None = None
    evidence_urls: list[str] = []
    user_nickname: str | None = None
    user_phone: str | None = None
    order_tier: str
    paid_at: str | None = None
    created_at: str | None = None


class AdminRefundListOut(BaseModel):
    total: int
    items: list[AdminRefundItem]


class RefundReviewRequest(BaseModel):
    approve: bool
    amount_fen: int | None = Field(None, description="核定退款金额（分）；空则用记录原金额")
    reason: str | None = None


# ── 收款主体（多主体/多渠道）────────────────────────────────────────────────


class PaymentAccountItem(BaseModel):
    id: uuid.UUID
    name: str
    subject_type: str = Field(..., description="individual | company | subsidiary")
    provider: str = Field(..., description="wechat | alipay | apple_iap | ...")
    config: dict = {}
    secret_alias: str | None = None
    branch_company_id: uuid.UUID | None = None
    is_default: bool
    is_active: bool
    credentials_ready: bool = Field(..., description="所需密钥是否已在 env 就绪（不含密钥值）")
    required_secret_keys: list[str] = []
    created_at: str | None = None


class PaymentAccountCreate(BaseModel):
    name: str
    subject_type: str = "company"
    provider: str = "wechat"
    config: dict | None = Field(None, description="渠道非密身份，如微信 {mch_id,cert_serial}")
    secret_alias: str | None = Field(None, description="env 密钥别名，密钥本身不入库")
    branch_company_id: uuid.UUID | None = None
    is_active: bool = True


class PaymentAccountUpdate(BaseModel):
    name: str | None = None
    subject_type: str | None = None
    provider: str | None = None
    config: dict | None = None
    secret_alias: str | None = None
    branch_company_id: uuid.UUID | None = None
    is_active: bool | None = None


# ── 支付参数 ──────────────────────────────────────────────────────────────────


class PayParamsOut(BaseModel):
    """POST /orders/{id}/pay 响应体，前端传给 wx.requestPayment()。"""

    timeStamp: str
    nonceStr: str
    package: str = Field(..., description="prepay_id=wx...")
    signType: str = Field(default="RSA")
    paySign: str
