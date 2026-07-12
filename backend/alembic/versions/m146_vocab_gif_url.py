"""词力通媒体:vocabulary_words 加 gif_url(动词/动作词的关键帧 GIF 动图)

Revision ID: m146_vocab_gif_url
Revises: m145_drop_legacy_kp_tables
"""
import sqlalchemy as sa
from alembic import op

revision = "m146_vocab_gif_url"
down_revision = "m145_drop_legacy_kp_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等:多 head 遗留环境下可能被 dev 手动加过,IF NOT EXISTS 避免二次失败
    op.execute("ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS gif_url varchar")


def downgrade() -> None:
    op.execute("ALTER TABLE vocabulary_words DROP COLUMN IF EXISTS gif_url")

