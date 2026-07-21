"""merge heads:统一历史多分支为单头,修复 deploy 的 `alembic upgrade head`(多头会报错)。无 DDL。

Revision ID: m190_merge_heads
Revises: m136_reach_ab, m146_vocab_gif_url, m177_student_grammar_practice, m189_vocab_kp_mcq_revision
Create Date: 2026-07-20
"""
revision = "m190_merge_heads"
down_revision = ("m136_reach_ab", "m146_vocab_gif_url", "m177_student_grammar_practice", "m189_vocab_kp_mcq_revision")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
