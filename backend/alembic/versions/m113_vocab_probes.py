"""R9.1 词汇可输入性理解:词级探针库 + 接收/产出双维掌握度。

Revision ID: m113_vocab_probes
Revises: m112_llm_usage_log
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m113_vocab_probes"
down_revision = "m112_llm_usage_log"
branch_labels = None
depends_on = None


def _cols(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    vw = _cols("vocabulary_words")
    if "probes_json" not in vw:
        op.add_column("vocabulary_words", sa.Column("probes_json", JSONB(), nullable=True))
    vl = _cols("vocabulary_learning")
    if "mastery_recep" not in vl:
        op.add_column("vocabulary_learning", sa.Column("mastery_recep", sa.Numeric(5, 4), nullable=True))
    if "mastery_prod" not in vl:
        op.add_column("vocabulary_learning", sa.Column("mastery_prod", sa.Numeric(5, 4), nullable=True))
    if "transfer_ok" not in vl:
        op.add_column("vocabulary_learning", sa.Column(
            "transfer_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade():
    for t, c in (("vocabulary_words", "probes_json"), ("vocabulary_learning", "mastery_recep"),
                 ("vocabulary_learning", "mastery_prod"), ("vocabulary_learning", "transfer_ok")):
        if c in _cols(t):
            op.drop_column(t, c)
