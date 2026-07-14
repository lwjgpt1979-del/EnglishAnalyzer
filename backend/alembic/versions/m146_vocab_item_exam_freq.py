"""真题词频反哺:vocab_list_item 加 added_from_exam(标真题补录词,区分考纲原生)

frequency 列复用为「中考真题卷频次」,star 复用为高/中/低频档(3/2/1/0);
added_from_exam=true 表示该词考纲原本没有、因出现在真题里被补录。

Revision ID: m146_vocab_item_exam_freq
Revises: m145_drop_legacy_kp_tables
"""
from alembic import op
import sqlalchemy as sa

revision = "m146_vocab_item_exam_freq"
down_revision = "m145_drop_legacy_kp_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vocab_list_item",
        sa.Column("added_from_exam", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("vocab_list_item", "added_from_exam")
