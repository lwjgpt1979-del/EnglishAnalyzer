"""vocab_kp_mcq.dimension 扩宽 16→32(动态维度键如 prep_discrimination 超 16)。幂等。

Revision ID: m186_vocab_kp_mcq_dim32
Revises: m185_student_wrong_word
Create Date: 2026-07-20
"""
from alembic import op

revision = "m186_vocab_kp_mcq_dim32"
down_revision = "m185_student_wrong_word"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE vocab_kp_mcq ALTER COLUMN dimension TYPE VARCHAR(32)")


def downgrade():
    pass   # 收窄可能截断,不回退
