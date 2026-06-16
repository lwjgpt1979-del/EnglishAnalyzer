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
    addon_feature_key = mapped_column(sa.String(64), nullable=True)   # 加量包：购买的功能能力键

    # —— 退款 / 申诉（§4.5，状态码用 VARCHAR 存，避免 PG 枚举迁移）——
    refund_status = mapped_column(
        sa.String, nullable=False, server_default=sa.text("'NONE'")
    )
    appeal_status = mapped_column(
        sa.String, nullable=False, server_default=sa.text("'NONE'")
    )
    is_promotional = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    total_days = mapped_column(sa.Integer, nullable=True)  # 下单时 = duration_months×30
    payment_confirm_log_id = mapped_column(UUID(as_uuid=True), nullable=True)
    # 这笔钱由哪个收款主体收的（下单固化；退款按此原路退回，支持多主体/多渠道）
    payment_account_id = mapped_column(UUID(as_uuid=True), nullable=True)
    # —— 优惠券抵扣（SP-4）——
    coupon_grant_id = mapped_column(UUID(as_uuid=True), nullable=True)
    discount_fen = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )  # 已抵扣金额（amount_fen 已是抵扣后实付）

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
    # 退款异步对账：out_refund_no 匹配微信退款结果通知；wx_refund_status 存原始状态
    out_refund_no = mapped_column(sa.String, nullable=True, index=True)
    wx_refund_status = mapped_column(sa.String, nullable=True)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    # G22: 审核人，platform_admin 操作退款审核时填写
    reviewed_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    # —— 申诉/决策树扩展（§4.5）——
    appeal_type = mapped_column(sa.String, nullable=True)   # SYSTEM_FAULT/DESC_MISMATCH/DUPLICATE_PURCHASE/MINOR_PURCHASE
    state_code = mapped_column(sa.String, nullable=True)    # 决策树结果码（AUTO_FULL_REFUND 等）
    evidence_urls = mapped_column(JSONB, nullable=True)     # 申诉证明截图 URL 列表
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class InvoiceRequest(Base):
    """发票申请记录（§5.4）。应用内只管申请+状态；真实发票走税控/电子发票服务商。

    开票方=订单收款主体（payment_account_id 固化），适配主体演进。
    """

    __tablename__ = "invoice_requests"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    order_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False)
    payment_account_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 开票主体
    title_type = mapped_column(sa.String, nullable=False, server_default=sa.text("'personal'"))  # personal|company
    title = mapped_column(sa.String, nullable=False)         # 抬头
    tax_no = mapped_column(sa.String, nullable=True)          # 企业税号
    amount_fen = mapped_column(sa.Integer, nullable=False)
    content = mapped_column(sa.String, nullable=True)         # 开票内容
    email = mapped_column(sa.String, nullable=True)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'pending'"))  # pending|issued|rejected
    invoice_no = mapped_column(sa.String, nullable=True)
    invoice_url = mapped_column(sa.String, nullable=True)
    note = mapped_column(sa.Text, nullable=True)
    issued_by = mapped_column(UUID(as_uuid=True), nullable=True)
    issued_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class PaymentConfirmLog(Base):
    """支付前合规确认留存（§4.5.2 / §4.6），举证用，禁物理删（archived 逻辑归档）。"""

    __tablename__ = "payment_confirm_logs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    order_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True
    )
    confirmed_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    ip_address = mapped_column(sa.String, nullable=True)
    device_id = mapped_column(sa.String, nullable=True)
    session_id = mapped_column(sa.String, nullable=True)
    user_agent = mapped_column(sa.Text, nullable=True)
    checkbox_refund_policy = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    checkbox_digital_service = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    plan_snapshot = mapped_column(JSONB, nullable=True)
    archived = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


# ─── 机构学生采购（D-122）────────────────────────────────────────────────────


class InstitutionPurchase(Base):
    __tablename__ = "institution_purchases"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=False
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    quantity = mapped_column(sa.Integer, nullable=False)
    amount_fen = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'paid'"))
    created_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ActivationCode(Base):
    __tablename__ = "activation_codes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String(12), nullable=False, unique=True)
    purchase_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institution_purchases.id"), nullable=False
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'unused'"))
    used_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    used_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class Coupon(Base):
    """优惠券模板（SP-4）。

    支持两种发放：
      1) 后台直接发券给指定用户 → 直接创建 CouponGrant。
      2) 兑换码批量发放：设 redeem_code（公开码），用户输入后领取一张 grant，
         redeem_quota 控制总领取量，per_user_limit 控制每人领取次数。
    抵扣类型：amount(满减，discount_value=分) | percent(折扣，discount_value=万分比，9500=95折)。
    """

    __tablename__ = "coupons"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(100), nullable=False)
    discount_type = mapped_column(sa.String(10), nullable=False)   # amount|percent
    discount_value = mapped_column(sa.Integer, nullable=False)     # 分 或 万分比
    min_amount_fen = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    max_discount_fen = mapped_column(sa.Integer, nullable=True)    # percent 券封顶
    scope = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'all'"))  # all|semester|addon|renew
    redeem_code = mapped_column(sa.String(20), nullable=True, unique=True)  # 兑换码（可空=仅后台直发）
    redeem_quota = mapped_column(sa.Integer, nullable=True)        # 兑换码总量（null=不限）
    redeemed_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    per_user_limit = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    valid_from = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    valid_until = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_active = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_by = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class CouponGrant(Base):
    """用户持有的一张优惠券（SP-4）。下单时选用 → 支付成功标记 used。"""

    __tablename__ = "coupon_grants"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("coupons.id"), nullable=False
    )
    user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    status = mapped_column(sa.String(10), nullable=False, server_default=sa.text("'unused'"))  # unused|used
    order_id = mapped_column(UUID(as_uuid=True), nullable=True)
    used_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
