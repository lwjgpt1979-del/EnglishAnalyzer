"""域14: V2 学期会员 (1 张表)
  purchased_semesters
"""
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column
from .base import Base
from .d1_users import semester_enum
from .d2_payments import order_tier_enum


class PurchasedSemester(Base):
    """用户已购买的学期会员。一行 = 一个 (用户, 教材, 年级, 学期, 档位, 6 个月有效期)。"""
    __tablename__ = "purchased_semesters"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    textbook_version = mapped_column(sa.String, nullable=False)
    grade = mapped_column(sa.String, nullable=False)
    semester = mapped_column(semester_enum, nullable=False)
    tier = mapped_column(order_tier_enum, nullable=False)
    semester_no = mapped_column(sa.SmallInteger, nullable=False)
    started_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    order_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_purchased_semesters_user_lookup",
                 "user_id", "textbook_version", "grade", "semester"),
    )
