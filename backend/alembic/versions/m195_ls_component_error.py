"""句子成分理解·细分错误 tally(方案B):ls_component_error。幂等。

Revision ID: m195_ls_component_error
Revises: m194_wrong_record_practice
Create Date: 2026-07-22
"""
from alembic import op

revision = "m195_ls_component_error"
down_revision = "m194_wrong_record_practice"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS ls_component_error (
            id UUID PRIMARY KEY,
            student_id UUID NOT NULL,
            sentence_md5 VARCHAR(32) NOT NULL,
            sentence TEXT,
            skill VARCHAR(12) NOT NULL,
            role VARCHAR(24) NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            streak SMALLINT NOT NULL DEFAULT 0,
            last_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_ls_component_error UNIQUE (student_id, sentence_md5, skill, role)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ls_component_error_student ON ls_component_error(student_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS ls_component_error")
