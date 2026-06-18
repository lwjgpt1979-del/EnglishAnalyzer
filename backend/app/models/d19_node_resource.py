"""域19: 知识节点资源(KP-First R6)。

通用资源表挂 knowledge_nodes,承载多类型学习资源:
  lecture(六维度讲解)/ video(视频)/ example(例句库)/ essay(写作范文)/ mindmap(思维导图)。
旧 knowledge_point_contents(挂旧 KP)保留不动、不桥接;新资源走本表。
枚举字段用 varchar(同 d15+ 风格),取值 service 层校验。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class NodeResource(Base):
    """知识节点学习资源(多类型)。"""

    __tablename__ = "node_resource"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    resource_type = mapped_column(sa.String(16), nullable=False)   # lecture|video|example|essay|mindmap
    dimension = mapped_column(sa.String(16), nullable=True)        # 仅 lecture:听/词汇/语法/阅读/翻译/写作
    title = mapped_column(sa.String(200), nullable=True)
    content_md = mapped_column(sa.Text, nullable=True)             # 讲解/范文正文
    media_url = mapped_column(sa.String(512), nullable=True)       # 视频/音频/思维导图图 直链
    resource_json = mapped_column(JSONB, nullable=True)           # 例句数组 / 思维导图树
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))  # draft|reviewing|published|retired
    generated_by = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'manual'"))  # ai_full|ai_with_human_review|manual|imported
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    reviewed_by = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        # lecture 每维度一条(dimension 非空);其它类型 dimension=null → PG NULL 互异 → 可多条
        sa.UniqueConstraint("node_id", "resource_type", "dimension", name="uix_node_resource_identity"),
        sa.Index("ix_node_resource_node_type", "node_id", "resource_type"),
        sa.Index("ix_node_resource_status", "status"),
    )
