"""
域10: 分公司扩展 (3 张表)
  branch_companies · branch_company_cities · branch_settlements
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base

settlement_status_enum = sa.Enum(
    "draft", "confirmed", "paid",
    name="settlement_status",
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
