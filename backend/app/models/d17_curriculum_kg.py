"""域17: 教材接入 KP-First(R1)。

单元 ↔ 知识节点 多对多边(指向**新** knowledge_nodes,与旧 unit_knowledge_points 并存)。
教材单元抽取出的知识点名经 kp_match_service 受控匹配命中后,在此建边;
一单元多 KP、一 KP 被多单元引用(KP-First 必然)。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class UnitNode(Base):
    """教材单元 ↔ 知识节点 边(R1)。"""

    __tablename__ = "unit_node"

    unit_id = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("curriculum_units.id", ondelete="CASCADE"),
        primary_key=True,
    )
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    source = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'ai_extract'"))  # ai_extract|upload_extract|manual
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.Index("ix_unit_node_node", "node_id"),
    )
