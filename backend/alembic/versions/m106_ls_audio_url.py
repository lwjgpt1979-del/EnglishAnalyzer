"""long_sentence 加 audio_url:听原句 TTS 首次合成→存 COS→回填直链,再次直接播。

Revision ID: m106_ls_audio_url
Revises: m105_sim_version
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "m106_ls_audio_url"
down_revision = "m105_sim_version"
branch_labels = None
depends_on = None


def _has_col(c):
    return any(col["name"] == c for col in sa.inspect(op.get_bind()).get_columns("long_sentence"))


def upgrade():
    if not _has_col("audio_url"):
        op.add_column("long_sentence", sa.Column("audio_url", sa.Text(), nullable=True))


def downgrade():
    if _has_col("audio_url"):
        op.drop_column("long_sentence", "audio_url")
