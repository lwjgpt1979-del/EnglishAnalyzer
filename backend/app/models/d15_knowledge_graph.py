"""域15: 知识图谱骨架（KP-First 重构 R0）。

多轴知识节点 + 别名归一 + 节点关系 + 候选审核。
枚举类字段一律用 varchar（轴/状态/来源等结构性小集合），避免 PG 枚举迁移摩擦，
与重构"可演进不写死枚举"的原则一致；取值合法性在 service 层校验。

与现有 d4_knowledge.KnowledgePoint(knowledge_points) 并存：R0 不动旧表，
新抽取/新功能写本域，旧模块仍读旧表，R1+ 逐步切换。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from .base import Base


class KnowledgeNode(Base):
    """多轴知识节点（R0 §2.1）。axis 决定属于哪棵树。"""

    __tablename__ = "knowledge_nodes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    axis = mapped_column(sa.String(12), nullable=False)          # knowledge|ability|exam
    node_kind = mapped_column(sa.String(32), nullable=True)      # 轴内子类型（词汇/听/题型…）
    parent_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True
    )
    name = mapped_column(sa.String(120), nullable=False)
    code = mapped_column(sa.String(64), nullable=False, unique=True)   # 稳定编码（非随机 auto_）
    applicable_stages = mapped_column(JSONB, nullable=True)      # ["小","初","高"]
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'active'"))  # active|candidate|retired
    source = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'seed'"))    # seed|textbook|exam
    description = mapped_column(sa.Text, nullable=True)
    sort_order = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.Index("ix_knowledge_nodes_axis_parent", "axis", "parent_id"),
        sa.Index("ix_knowledge_nodes_status", "status"),
    )


class NodeAlias(Base):
    """节点别名归一（R0 §2.2）。alias_norm 全局唯一 → 一个写法只指一个节点，杜绝碎片化。"""

    __tablename__ = "knowledge_node_aliases"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=False
    )
    alias = mapped_column(sa.String(120), nullable=False)
    alias_norm = mapped_column(sa.String(120), nullable=False, unique=True)
    source = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'seed'"))  # seed|merge|extract
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.Index("ix_node_aliases_node", "node_id"),
    )


class NodeRelation(Base):
    """轴间/同轴弱关系（R0 §2.3）。R0 建表，关系数据后续补。"""

    __tablename__ = "knowledge_node_relations"

    from_node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    to_node_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    relation = mapped_column(sa.String(16), primary_key=True)   # related|assessed_by|prereq
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class KpCandidate(Base):
    """候选知识点 + 审核（R0 §2.4）。受控匹配未命中 → 在此累加，超管审核入库/合并/驳回。"""

    __tablename__ = "kp_candidates"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_name = mapped_column(sa.String(120), nullable=False)
    name_norm = mapped_column(sa.String(120), nullable=False)
    suggested_axis = mapped_column(sa.String(12), nullable=True)
    suggested_stage = mapped_column(sa.String(8), nullable=True)
    occur_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    context_sample = mapped_column(JSONB, nullable=True)
    source_type = mapped_column(sa.String(24), nullable=True)   # textbook|exam|uploaded_student|uploaded_institution
    source_ref = mapped_column(JSONB, nullable=True)
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'pending'"))  # pending|approved|merged|rejected
    merged_into_node_id = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("name_norm", "suggested_axis", name="uix_kp_candidate_norm_axis"),
        sa.Index("ix_kp_candidates_status", "status", "occur_count"),
    )
