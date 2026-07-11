"""student_kp_target:学习目标表(未学/薄弱考点加入 → 今日计划)。幂等。

Revision ID: m148_student_kp_target
Revises: m147_ups_suggested
Create Date: 2026-07-08
"""
from alembic import op

revision = "m148_student_kp_target"
down_revision = "m147_ups_suggested"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_kp_target (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL REFERENCES users(id),
            node_id UUID NOT NULL REFERENCES knowledge_nodes(id),
            source VARCHAR(24) NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_student_kp_target UNIQUE (student_id, node_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_kp_target_student ON student_kp_target (student_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS student_kp_target")
