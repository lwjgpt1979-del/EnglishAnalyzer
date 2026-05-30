"""
域2: 会员与支付 (3 张表)
  memberships · orders · refund_records

注意: Order 必须在 Membership 之前定义，因为 memberships.order_id FK 引用 orders。
branch_companies 在域10定义，FK 用字符串引用（SQLAlchemy 延迟解析）。
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

membership_tier_enum = sa.Enum(
    "free", "basic", "pro", "promax",
    name="membership_tier",
)
# orders 的 tier 不含 free（仅付费档）
order_tier_enum = sa.Enum(
    "basic", "pro", "promax",
    name="order_tier",
)
order_type_enum = sa.Enum(
    "new", "renew", "upgrade",
    name="order_type",
)
order_status_enum = sa.Enum(
    "pending", "paid", "refunded", "partial_refunded",
    name="order_status",
)
refund_type_enum = sa.Enum(
    "standard_7d", "prorated", "appeal",
    name="refund_type",
)
refund_status_enum = sa.Enum(
    "pending", "approved", "rejected", "completed",
    name="refund_status",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class Order(Base):
    """先建 Order，Membership 的 order_id FK 才能引用它。"""

    __tablename__ = "orders"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_no = mapped_column(sa.String, nullable=False, unique=True)
    payer_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    beneficiary_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    order_type = mapped_column(order_type_enum, nullable=False)
    tier = mapped_column(order_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    amount_fen = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(order_status_enum, nullable=False)
    wx_transaction_id = mapped_column(sa.String, nullable=True)
    paid_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    # branch_companies 在域10定义，字符串 FK 由 SQLAlchemy 延迟解析
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    platform_income_fen = mapped_column(sa.Integer, nullable=True)
    branch_commission_fen = mapped_column(sa.Integer, nullable=True)
    institution_commission_fen = mapped_column(sa.Integer, nullable=True)
    # —— V2 学期会员（D-079 / M1）——
    semester_count = mapped_column(sa.SmallInteger, nullable=True)
    purchased_semester_ids = mapped_column(JSONB, nullable=True)

    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Membership(Base):
    """
    会员记录。每个用户同时只有一条 is_active=true 的记录（部分唯一索引保证）。
    order_id (G19): 关联触发本次会员的订单，用于幂等校验与审计。
    """

    __tablename__ = "memberships"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    # G19: 关联触发订单，nullable 允许历史数据或免费会员
    order_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    started_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )

    __table_args__ = (
        sa.Index(
            "uix_memberships_user_active",
            "user_id",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )


class RefundRecord(Base):
    __tablename__ = "refund_records"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False
    )
    amount_fen = mapped_column(sa.Integer, nullable=False)
    refund_type = mapped_column(refund_type_enum, nullable=False)
    status = mapped_column(refund_status_enum, nullable=False)
    reason = mapped_column(sa.Text, nullable=True)
    wx_refund_id = mapped_column(sa.String, nullable=True)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    # G22: 审核人，platform_admin 操作退款审核时填写
    reviewed_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
