"""知识树叶子考点标「初」学段:现有 286 个四段考点(cf/jf-n-n-n)= 中考(初中)内容。

一棵树 + 学段标签(小/初/高)区分覆盖范围:分类/中间节点留 null(通用脚手架,各学段共用),
仅叶子考点带学段。现有内容来自中考《考频分区速学》→ 全标「初」;以后小学/高中考点加进
同一棵树并标各自学段(共享考点可标多学段)。AI 建议/匹配按题/卷学段软过滤候选考点。

Revision ID: m99_tag_stage
Revises: m98_drop_axis
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "m99_tag_stage"
down_revision = "m98_drop_axis"
branch_labels = None
depends_on = None

_LEAF_RE = r"^(cf|jf)-[0-9]+-[0-9]+-[0-9]+$"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE knowledge_nodes SET applicable_stages = '[\"初\"]'::jsonb "
        "WHERE axis = 'knowledge' AND applicable_stages IS NULL AND code ~ :re"),
        {"re": _LEAF_RE})


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE knowledge_nodes SET applicable_stages = NULL "
        "WHERE axis = 'knowledge' AND applicable_stages = '[\"初\"]'::jsonb AND code ~ :re"),
        {"re": _LEAF_RE})
