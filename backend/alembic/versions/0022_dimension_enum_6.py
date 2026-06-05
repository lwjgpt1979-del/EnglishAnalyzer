"""dimension_enum_6: content_dimension 4→6（+vocabulary/reading/translation, -dictation）

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-06
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # content_dimension 同时被 knowledge_point_contents.dimension 和
    # simulated_questions.dimension（0014 加）引用，不能直接 DROP TYPE。
    # 用 rename → create new → ALTER COLUMN ... USING → drop old 的方式原地迁移，
    # 旧值 'dictation' 映射为 'writing'（听写已并入写作维度）。
    op.execute("ALTER TYPE content_dimension RENAME TO content_dimension_old")
    op.execute(
        "CREATE TYPE content_dimension AS ENUM "
        "('listening', 'vocabulary', 'grammar', 'reading', 'translation', 'writing')"
    )
    for table in ("knowledge_point_contents", "simulated_questions"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN dimension TYPE content_dimension "
            "USING (CASE WHEN dimension::text = 'dictation' THEN 'writing' "
            "ELSE dimension::text END::content_dimension)"
        )
    op.execute("DROP TYPE content_dimension_old")


def downgrade() -> None:
    # 反向：6 维度 → 4 维度。新增的 vocabulary/reading/translation 值映射回 grammar
    # （无精确逆映射；选 grammar 作为兜底，保证 cast 不失败）。
    op.execute("ALTER TYPE content_dimension RENAME TO content_dimension_new")
    op.execute(
        "CREATE TYPE content_dimension AS ENUM "
        "('listening', 'dictation', 'grammar', 'writing')"
    )
    for table in ("knowledge_point_contents", "simulated_questions"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN dimension TYPE content_dimension "
            "USING (CASE WHEN dimension::text IN ('vocabulary', 'reading', 'translation') "
            "THEN 'grammar' ELSE dimension::text END::content_dimension)"
        )
    op.execute("DROP TYPE content_dimension_new")
