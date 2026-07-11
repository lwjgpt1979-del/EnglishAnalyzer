"""整卷「大题/板块」结构:新增 user_paper_sections + user_paper_questions 加
section_id / passage / block_key / sort_order,还原原卷题型结构。幂等(IF NOT EXISTS)。

Revision ID: m146_user_paper_sections
Revises: m145_drop_legacy_kp_tables
Create Date: 2026-07-08
"""
from alembic import op

revision = "m146_user_paper_sections"
down_revision = "m145_drop_legacy_kp_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_paper_sections (
            id UUID PRIMARY KEY,
            user_paper_id UUID NOT NULL REFERENCES user_uploaded_papers(id),
            label VARCHAR NOT NULL,
            section_type VARCHAR,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_paper_sections_paper ON user_paper_sections (user_paper_id)")
    op.execute("ALTER TABLE user_paper_questions ADD COLUMN IF NOT EXISTS section_id UUID REFERENCES user_paper_sections(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE user_paper_questions ADD COLUMN IF NOT EXISTS passage TEXT")
    op.execute("ALTER TABLE user_paper_questions ADD COLUMN IF NOT EXISTS block_key VARCHAR")
    op.execute("ALTER TABLE user_paper_questions ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS section_id")
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS passage")
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS block_key")
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS sort_order")
    op.execute("DROP TABLE IF EXISTS user_paper_sections")
