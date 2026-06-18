"""词汇接入 KP-First（R5.1）：VocabularyWord 扩字段 + 词↔KP/真题/错题边 + 通用词库。

vocabulary_words 加 type/source/frequency/star;新建 vocab_node / vocab_question /
vocab_wrong / vocab_list / vocab_list_item。带存在性保护。

Revision ID: m87_vocab_kg
Revises: m86_wrong_record_sm2
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "m87_vocab_kg"
down_revision = "m86_wrong_record_sm2"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has(t):
    return t in _insp().get_table_names()


def _cols(t):
    return {c["name"] for c in _insp().get_columns(t)}


def upgrade() -> None:
    cols = _cols("vocabulary_words")
    add = [
        ("type", sa.Column("type", sa.String(12), nullable=False, server_default="word")),
        ("source", sa.Column("source", sa.String(16), nullable=True)),
        ("frequency", sa.Column("frequency", sa.Integer(), nullable=True)),
        ("star", sa.Column("star", sa.SmallInteger(), nullable=False, server_default="0")),
    ]
    for name, col in add:
        if name not in cols:
            op.add_column("vocabulary_words", col)

    if not _has("vocab_node"):
        op.create_table(
            "vocab_node",
            sa.Column("word_id", UUID(as_uuid=True),
                      sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
            sa.Column("source", sa.String(16), nullable=False, server_default="textbook"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_vocab_node_node", "vocab_node", ["node_id"])

    if not _has("vocab_question"):
        op.create_table(
            "vocab_question",
            sa.Column("word_id", UUID(as_uuid=True),
                      sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("q_scope", sa.String(12), primary_key=True),
            sa.Column("question_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("source", sa.String(16), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    if not _has("vocab_wrong"):
        op.create_table(
            "vocab_wrong",
            sa.Column("word_id", UUID(as_uuid=True),
                      sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("wrong_record_id", UUID(as_uuid=True),
                      sa.ForeignKey("wrong_record.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    if not _has("vocab_list"):
        op.create_table(
            "vocab_list",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("exam_level", sa.String(32), nullable=True),
            sa.Column("source_type", sa.String(24), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("maintained_by", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    if not _has("vocab_list_item"):
        op.create_table(
            "vocab_list_item",
            sa.Column("list_id", UUID(as_uuid=True),
                      sa.ForeignKey("vocab_list.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("word_id", UUID(as_uuid=True),
                      sa.ForeignKey("vocabulary_words.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("frequency", sa.Integer(), nullable=True),
            sa.Column("star", sa.SmallInteger(), nullable=False, server_default="0"),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        )
        op.create_index("ix_vocab_list_item_word", "vocab_list_item", ["word_id"])


def downgrade() -> None:
    for t in ("vocab_list_item", "vocab_list", "vocab_wrong", "vocab_question", "vocab_node"):
        if _has(t):
            op.drop_table(t)
    cols = _cols("vocabulary_words")
    for name in ("star", "frequency", "source", "type"):
        if name in cols:
            op.drop_column("vocabulary_words", name)
