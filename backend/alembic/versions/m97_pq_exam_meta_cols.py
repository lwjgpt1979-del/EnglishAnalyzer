"""platform_question 落可筛选字段(教材/学段/年级/上下册/地区/考试类型)+ 从 meta 回填。

Revision ID: m97_pq_exam_cols
Revises: m96_platform_paper
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "m97_pq_exam_cols"
down_revision = "m96_platform_paper"
branch_labels = None
depends_on = None

_COLS = [
    ("textbook_version", sa.String(24)),
    ("stage", sa.String(8)),
    ("grade", sa.String(12)),
    ("semester", sa.String(4)),
    ("region_code", sa.String(12)),
    ("region_name", sa.String(64)),
    ("exam_type", sa.String(12)),
]


def _has_col(c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns("platform_question"))


def upgrade() -> None:
    for name, typ in _COLS:
        if not _has_col(name):
            op.add_column("platform_question", sa.Column(name, typ, nullable=True))
    op.create_index("ix_platform_question_book", "platform_question",
                    ["textbook_version", "stage", "grade"], if_not_exists=True)
    op.create_index("ix_platform_question_region", "platform_question",
                    ["region_code"], if_not_exists=True)
    op.create_index("ix_platform_question_exam", "platform_question",
                    ["exam_type"], if_not_exists=True)
    # 回填:从既有 meta JSONB 提取(仅回填当前为空的列)
    op.execute("""
        UPDATE platform_question SET
          textbook_version = COALESCE(textbook_version, meta->>'textbook_version'),
          stage            = COALESCE(stage,            meta->>'stage'),
          grade            = COALESCE(grade,            meta->>'grade'),
          semester         = COALESCE(semester,         meta->>'semester'),
          region_code      = COALESCE(region_code,      meta->>'city_code', meta->>'region_code'),
          region_name      = COALESCE(region_name,      meta->>'region_name'),
          exam_type        = COALESCE(exam_type,        meta->>'exam_type')
        WHERE meta IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_platform_question_exam", table_name="platform_question", if_exists=True)
    op.drop_index("ix_platform_question_region", table_name="platform_question", if_exists=True)
    op.drop_index("ix_platform_question_book", table_name="platform_question", if_exists=True)
    for name, _ in _COLS:
        if _has_col(name):
            op.drop_column("platform_question", name)
