"""R10.1 语法掌握:KnowledgePoint 加 grammar_probes_json(词级公共探针缓存)
+ 新表 student_grammar_mastery(个性化四维 BKT,镜像 R9 VocabularyLearning)。

Revision ID: m115_grammar_probes
Revises: m114_vocab_pin_priority
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m115_grammar_probes"
down_revision = "m114_vocab_pin_priority"
branch_labels = None
depends_on = None


def _cols(t):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(t)}


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if "grammar_probes_json" not in _cols("knowledge_points"):
        op.add_column("knowledge_points",
                      sa.Column("grammar_probes_json", JSONB(), nullable=True))

    if "student_grammar_mastery" not in _tables():
        op.create_table(
            "student_grammar_mastery",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("student_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kp_id", UUID(as_uuid=True),
                      sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
            # 四维 BKT(R10.1 用 recognize/detect;produce/transfer 留 R10.2/3)
            sa.Column("mastery_recognize", sa.Numeric(5, 4), nullable=True),
            sa.Column("mastery_detect", sa.Numeric(5, 4), nullable=True),
            sa.Column("mastery_produce", sa.Numeric(5, 4), nullable=True),
            sa.Column("transfer_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            # 先验来源:default/placement/paper/learn
            sa.Column("prior_source", sa.String(16), nullable=False, server_default=sa.text("'default'")),
            sa.Column("wrong_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("last_retain_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.UniqueConstraint("student_id", "kp_id", name="uq_sgm_student_kp"),
        )


def downgrade():
    if "student_grammar_mastery" in _tables():
        op.drop_table("student_grammar_mastery")
    if "grammar_probes_json" in _cols("knowledge_points"):
        op.drop_column("knowledge_points", "grammar_probes_json")
