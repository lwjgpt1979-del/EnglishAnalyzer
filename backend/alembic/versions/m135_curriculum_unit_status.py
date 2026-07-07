"""curriculum_units 加发布闸门 status(draft/published):整理好再发布,学生只见 published。

存量单元回填 published(保持既有可见性);新建默认 draft。幂等(IF NOT EXISTS)。

Revision ID: m135_curriculum_unit_status
Revises: m133_task_run
Create Date: 2026-07-07
"""
from alembic import op

revision = "m135_curriculum_unit_status"
down_revision = "m133_task_run"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE curriculum_units ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'draft'")
    # 存量单元置 published:上线前无闸门、都可见,保持现状不因加闸门而全部消失
    op.execute("UPDATE curriculum_units SET status = 'published' WHERE status = 'draft'")


def downgrade():
    op.execute("ALTER TABLE curriculum_units DROP COLUMN IF EXISTS status")
