"""长难句解析(KP-First 句法轴):long_sentence + long_sentence_node。带存在性保护。

Revision ID: m90_long_sentence
Revises: m89_vocab_optin
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m90_long_sentence"
down_revision = "m89_vocab_optin"
branch_labels = None
depends_on = None


def _has(t):
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has("long_sentence"):
        op.create_table(
            "long_sentence",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("scope", sa.String(12), nullable=False, server_default="platform"),
            sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
            sa.Column("source_kind", sa.String(16), nullable=False),
            sa.Column("source_q_scope", sa.String(12), nullable=True),
            sa.Column("source_question_id", UUID(as_uuid=True), nullable=True),
            sa.Column("source_passage_id", UUID(as_uuid=True), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("analysis_json", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_long_sentence_source", "long_sentence", ["source_kind", "source_question_id"])
        op.create_index("ix_long_sentence_scope_status", "long_sentence", ["scope", "status"])

    if not _has("long_sentence_node"):
        op.create_table(
            "long_sentence_node",
            sa.Column("long_sentence_id", UUID(as_uuid=True),
                      sa.ForeignKey("long_sentence.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
        )
        op.create_index("ix_long_sentence_node_node", "long_sentence_node", ["node_id"])


def downgrade() -> None:
    for t in ("long_sentence_node", "long_sentence"):
        if _has(t):
            op.drop_table(t)
