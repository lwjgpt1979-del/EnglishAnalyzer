"""删除旧 node_resource 体系:node_resource_version / node_resource / pending_kp_content。

已被 kp_lecture(按考点类型的教学环节)整体取代,数据不迁移(不兼容重设计)。
先删有 FK 的 node_resource_version,再删 node_resource。幂等(IF EXISTS)。

Revision ID: m138_drop_node_resource
Revises: m137_kp_lecture
Create Date: 2026-07-07
"""
from alembic import op

revision = "m138_drop_node_resource"
down_revision = "m137_kp_lecture"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS node_resource_version")
    op.execute("DROP TABLE IF EXISTS node_resource")
    op.execute("DROP TABLE IF EXISTS pending_kp_content")


def downgrade():
    # 旧表结构不再维护;如需回滚请从 m88/m95 的建表定义恢复。
    pass
