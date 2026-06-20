"""知识图谱去 3 轴:删除 ability/题型(exam)轴节点 + 别名,只留知识分类树(F 方案)。

能力(听/说/读/写/译 5)+ 题型(8)节点仅被 knowledge_node_aliases 引用,无其它连带,删除安全。
axis 列保留(残留,恒为 'knowledge')。downgrade 从 seed 重建两轴。

Revision ID: m98_drop_axis
Revises: m97_pq_exam_cols
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "m98_drop_axis"
down_revision = "m97_pq_exam_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ids = bind.execute(sa.text(
        "SELECT id FROM knowledge_nodes WHERE axis IN ('ability','exam')")).scalars().all()
    if not ids:
        return
    bind.execute(sa.text("DELETE FROM knowledge_node_aliases WHERE node_id = ANY(:ids)"), {"ids": ids})
    bind.execute(sa.text("DELETE FROM knowledge_nodes WHERE id = ANY(:ids)"), {"ids": ids})


def downgrade() -> None:
    # 轴节点为 seed 数据,回滚由 seed 脚本重灌(此处不自动重建,避免 id 漂移)
    pass
