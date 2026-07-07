"""定时任务运行记录表 task_run(cron 任务运行留痕 + 失败告警)。

Revision ID: m133_task_run
Revises: m132_users_admin_modules
Create Date: 2026-07-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m133_task_run"
down_revision = "m132_users_admin_modules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task", sa.String(48), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_task_run_task_started", "task_run", ["task", "started_at"])


def downgrade():
    op.drop_index("ix_task_run_task_started", table_name="task_run")
    op.drop_table("task_run")
