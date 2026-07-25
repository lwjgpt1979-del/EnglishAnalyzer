"""作业阅读题·题型细标(reading_skill)——P1「阅读理解学情统计」。

给 user_paper_questions 加 reading_skill 列:细节理解/主旨大意/推理判断/词义猜测/
作者态度/指代关系/图表数字/其他。精讲时顺手写、存量从 reading_analysis_cache 回填、
未覆盖补跑归类。对错用现成 is_wrong,不新增表。幂等。

Revision ID: m197_reading_skill
Revises: m196_media_asset_ls_progress
Create Date: 2026-07-25
"""
from alembic import op

revision = "m197_reading_skill"
down_revision = "m196_media_asset_ls_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE user_paper_questions "
        "ADD COLUMN IF NOT EXISTS reading_skill VARCHAR(16)")
    # admin 归类页按题型筛选 / 学情按题型聚合
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_upq_reading_skill "
        "ON user_paper_questions (reading_skill)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_upq_reading_skill")
    op.execute("ALTER TABLE user_paper_questions DROP COLUMN IF EXISTS reading_skill")
