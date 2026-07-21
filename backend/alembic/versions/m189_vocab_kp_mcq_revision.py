"""vocab_kp_mcq_revision:考点题修改记录(AI 自动修正/人工编辑 before/after 快照)。幂等。

Revision ID: m189_vocab_kp_mcq_revision
Revises: m188_vocab_kp_mcq_report
Create Date: 2026-07-20
"""
from alembic import op

revision = "m189_vocab_kp_mcq_revision"
down_revision = "m188_vocab_kp_mcq_report"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocab_kp_mcq_revision (
            id UUID PRIMARY KEY,
            mcq_id UUID NOT NULL REFERENCES vocab_kp_mcq(id) ON DELETE CASCADE,
            before JSONB,
            after JSONB,
            trigger VARCHAR(8) NOT NULL,
            by_admin_id UUID,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_vocab_kp_mcq_revision_mcq ON vocab_kp_mcq_revision(mcq_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS vocab_kp_mcq_revision")
