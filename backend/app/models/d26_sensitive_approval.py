"""敏感操作二次审批(maker-checker)。

高风险操作(退款批准、批量发券)超阈值时不直接执行,先落一条 pending 审批,
由**另一位** platform_admin 复核批准后才执行(事前双人复核,补审计的事后追溯之不足)。
独立模块,避免与 admin.py 并发改动冲突。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class SensitiveApproval(Base):
    __tablename__ = "sensitive_approval"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type = mapped_column(sa.String(40), nullable=False)   # refund_approve | coupon_grant
    summary = mapped_column(sa.String(300), nullable=False)      # 人读摘要(谁/多少/给谁)
    payload = mapped_column(JSONB, nullable=False)               # 执行所需参数(批准时回放)
    amount_fen = mapped_column(sa.Integer, nullable=True)        # 金额(分)或规模,用于展示+阈值
    maker_id = mapped_column(UUID(as_uuid=True), nullable=False)  # 发起管理员
    maker_note = mapped_column(sa.String(500), nullable=True)
    # pending | approved(已批未执行,理论上瞬时) | executed | rejected | failed
    status = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'pending'"))
    checker_id = mapped_column(UUID(as_uuid=True), nullable=True)  # 复核管理员(≠ maker)
    checker_note = mapped_column(sa.String(500), nullable=True)
    exec_error = mapped_column(sa.String(500), nullable=True)      # 执行失败原因
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    decided_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
