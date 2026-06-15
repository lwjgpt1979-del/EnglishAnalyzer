"""
域10: 分公司扩展 (4 张表)
  branch_companies · branch_company_cities · branch_settlements · payment_accounts
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

settlement_status_enum = sa.Enum(
    "draft", "confirmed", "paid",
    name="settlement_status",
)


class PaymentAccount(Base):
    """收款主体 = 某支付渠道下的一个收款商户（= 一个营业执照主体）。

    渠道无关（provider-agnostic）：provider 决定用哪个适配器，config 存该渠道
    的非密身份（微信 {mch_id,cert_serial}、支付宝 {app_id,...}、苹果
    {issuer_id,key_id,bundle_id}…），加渠道不改表结构。
    支撑主体演进：个体 → 公司承接 → 总公司+地方子公司。订单下单时固化
    payment_account_id，退款按订单原主体/原渠道原路退回。
    **密钥（私钥/APIv3 key/.p8…）绝不入库**：仅存 secret_alias，运行时按
    alias 从环境变量读取（见 payment_account_service）。
    """

    __tablename__ = "payment_accounts"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String, nullable=False)  # 显示名，如 "XX教育科技公司"
    subject_type = mapped_column(
        sa.String, nullable=False, server_default=sa.text("'company'")
    )  # individual | company | subsidiary
    provider = mapped_column(
        sa.String, nullable=False, server_default=sa.text("'wechat'")
    )  # wechat | alipay | apple_iap | googleplay | stripe | ...
    # 渠道非密身份（各渠道字段不同）
    config = mapped_column(JSONB, nullable=True)
    # 加密存库的密钥：{key: AES-GCM 密文}，明文永不落库（见 core/crypto）
    secrets_enc = mapped_column(JSONB, nullable=True)
    # 兼容回退：指向 env 的密钥别名 PAY__<ALIAS>__<KEY>（secrets_enc 缺失时用）
    secret_alias = mapped_column(sa.String, nullable=True)
    # 子公司收款主体关联分公司；总公司/个体为 NULL
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True
    )
    is_default = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
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

    __table_args__ = (
        sa.Index(
            "uix_payment_accounts_default",
            "is_default",
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        ),
    )


class BranchCompany(Base):
    """分公司主档。bank_account 在应用层 AES-256-GCM 加密后存储。"""

    __tablename__ = "branch_companies"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String, nullable=False)
    contact_phone = mapped_column(sa.String, nullable=True)
    manager_user_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    commission_rate = mapped_column(sa.Numeric(5, 4), nullable=True)
    legal_name = mapped_column(sa.String, nullable=True)
    tax_number = mapped_column(sa.String, nullable=True)
    bank_name = mapped_column(sa.String, nullable=True)
    # AES-256-GCM 密文存储，解密在 service 层
    bank_account = mapped_column(sa.String, nullable=True)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
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


class BranchCompanyCity(Base):
    """分公司负责城市（同一时刻每个城市只能归属一家分公司）。"""

    __tablename__ = "branch_company_cities"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False
    )
    city_code = mapped_column(sa.String, nullable=False)
    effective_from = mapped_column(sa.Date, nullable=False)
    effective_to = mapped_column(sa.Date, nullable=True)
    # G16: 补充 created_at
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.Index(
            "uix_branch_company_cities_active_city",
            "city_code",
            unique=True,
            postgresql_where=sa.text("effective_to IS NULL"),
        ),
    )


class BranchSettlement(Base):
    """分公司对账结算单（G18: 补充 updated_at）。"""

    __tablename__ = "branch_settlements"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_company_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False
    )
    period_start = mapped_column(sa.Date, nullable=False)
    period_end = mapped_column(sa.Date, nullable=False)
    gross_revenue_fen = mapped_column(sa.Integer, nullable=False)
    refund_deduction_fen = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    net_revenue_fen = mapped_column(sa.Integer, nullable=False)
    platform_share_fen = mapped_column(sa.Integer, nullable=False)
    branch_payable_fen = mapped_column(sa.Integer, nullable=False)
    commission_rate_snapshot = mapped_column(sa.Numeric(5, 4), nullable=False)
    status = mapped_column(settlement_status_enum, nullable=False)
    confirmed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    paid_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    note = mapped_column(sa.Text, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # G18: 补充 updated_at（状态变更时更新）
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "branch_company_id", "period_start", "period_end",
            name="uix_branch_settlements_period",
        ),
    )
