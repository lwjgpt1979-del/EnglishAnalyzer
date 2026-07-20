"""vocab_word_relation 动态维度化:relation 扩宽为 dim_key(32),加 dim_label + sort。幂等。

Revision ID: m184_vocab_rel_dyn_dims
Revises: m183_student_wrong_relation
Create Date: 2026-07-20
"""
from alembic import op

revision = "m184_vocab_rel_dyn_dims"
down_revision = "m183_student_wrong_relation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_word_relation ALTER COLUMN relation TYPE VARCHAR(32)")
    op.execute("ALTER TABLE vocab_word_relation ADD COLUMN IF NOT EXISTS dim_label VARCHAR(32)")
    op.execute("ALTER TABLE vocab_word_relation ADD COLUMN IF NOT EXISTS sort SMALLINT NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE vocab_word_relation DROP COLUMN IF EXISTS sort")
    op.execute("ALTER TABLE vocab_word_relation DROP COLUMN IF EXISTS dim_label")
    # relation 保留 VARCHAR(32)(收窄可能截断,不回退)
