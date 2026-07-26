"""合并 7 个迁移头为单头,让 `alembic upgrade head` 能一路建到底(生产首发前置)。

历史 + 并行会话累积出 7 个头,`upgrade head` 遇多头直接报错、挡住全新生产库建表。
本 merge 仅收敛迁移拓扑(声明单头),**无任何 schema 变更**,不改动任何现有迁移文件。

Revision ID: m199_merge_heads
Revises: m146_vocab_gif_url, m189_vocab_kp_mcq_revision, m136_reach_ab,
         m197_essay_adapt_cache, 0025, m198_reading_answer_log, m177_student_grammar_practice
Create Date: 2026-07-26
"""

revision = "m199_merge_heads"
down_revision = (
    "m146_vocab_gif_url",
    "m189_vocab_kp_mcq_revision",
    "m136_reach_ab",
    "m197_essay_adapt_cache",
    "0025",
    "m198_reading_answer_log",
    "m177_student_grammar_practice",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
