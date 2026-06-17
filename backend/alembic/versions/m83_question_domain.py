"""题分域 + 个人窄表骨架（KP-First 重构 R0.5）：platform_question / uploaded_question /
passage / 两张题↔KP / student_kp / answer_log(月分区) / wrong_record。

按域物理分表,结构性隔离平台与个人。answer_log 建表即 RANGE(answered_at) 月分区 +
默认分区(决策⑤)。带存在性保护,可重复 upgrade head。R0.5 只建表,不灌数据。

Revision ID: m83_question_domain
Revises: m82_knowledge_graph
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "m83_question_domain"
down_revision = "m82_knowledge_graph"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has(t):
    return t in _insp().get_table_names()


def upgrade() -> None:
    # passage 先建(被 platform/uploaded 的 block_id 引用)
    if not _has("passage"):
        op.create_table(
            "passage",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("scope", sa.String(12), nullable=False),
            sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("audio_url", sa.String(512), nullable=True),
            sa.Column("source_ref", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_passage_scope_owner", "passage", ["scope", "owner_id"])

    if not _has("platform_question"):
        op.create_table(
            "platform_question",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("type", sa.String(8), nullable=False),
            sa.Column("parent_real_id", UUID(as_uuid=True), sa.ForeignKey("platform_question.id"), nullable=True),
            sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("block_id", UUID(as_uuid=True), sa.ForeignKey("passage.id"), nullable=True),
            sa.Column("question_no", sa.String(16), nullable=True),
            sa.Column("question_type", sa.String(16), nullable=True),
            sa.Column("stem", sa.Text(), nullable=True),
            sa.Column("options", JSONB(), nullable=True),
            sa.Column("answer", sa.Text(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("difficulty", sa.SmallInteger(), nullable=True),
            sa.Column("meta", JSONB(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_platform_question_type_status", "platform_question", ["type", "status"])
        op.create_index("ix_platform_question_parent", "platform_question", ["parent_real_id"])

    if not _has("uploaded_question"):
        op.create_table(
            "uploaded_question",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("owner_scope", sa.String(12), nullable=False),
            sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
            sa.Column("paper_id", UUID(as_uuid=True), nullable=True),
            sa.Column("block_id", UUID(as_uuid=True), sa.ForeignKey("passage.id"), nullable=True),
            sa.Column("question_no", sa.String(16), nullable=True),
            sa.Column("question_type", sa.String(16), nullable=True),
            sa.Column("stem", sa.Text(), nullable=True),
            sa.Column("student_answer", sa.Text(), nullable=True),
            sa.Column("correct_answer", sa.Text(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("is_wrong", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_uploaded_question_owner", "uploaded_question", ["owner_scope", "owner_id"])

    if not _has("platform_question_kp"):
        op.create_table(
            "platform_question_kp",
            sa.Column("question_id", UUID(as_uuid=True),
                      sa.ForeignKey("platform_question.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
        )

    if not _has("uploaded_question_kp"):
        op.create_table(
            "uploaded_question_kp",
            sa.Column("question_id", UUID(as_uuid=True),
                      sa.ForeignKey("uploaded_question.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
        )

    if not _has("student_kp"):
        op.create_table(
            "student_kp",
            sa.Column("student_id", UUID(as_uuid=True), primary_key=True),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), primary_key=True),
            sa.Column("mastery", sa.Numeric(5, 4), nullable=True),
            sa.Column("practice_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_practice_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_tags", ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("in_scope", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    # answer_log:RANGE(answered_at) 月分区 + 默认分区(op.create_table 不支持 PARTITION BY)
    if not _has("answer_log"):
        op.execute("""
            CREATE TABLE answer_log (
                id uuid NOT NULL,
                student_id uuid NOT NULL,
                q_scope varchar(12) NOT NULL,
                question_id uuid NOT NULL,
                is_correct boolean NOT NULL,
                feature varchar(24),
                answered_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (id, answered_at)
            ) PARTITION BY RANGE (answered_at)
        """)
        op.execute("CREATE TABLE answer_log_default PARTITION OF answer_log DEFAULT")
        op.execute("CREATE INDEX ix_answer_log_student_time ON answer_log (student_id, answered_at)")

    if not _has("wrong_record"):
        op.create_table(
            "wrong_record",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("q_scope", sa.String(12), nullable=False),
            sa.Column("question_id", UUID(as_uuid=True), nullable=False),
            sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_nodes.id"), nullable=True),
            sa.Column("is_original", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("status", sa.String(12), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("mastered_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_wrong_record_student_status", "wrong_record", ["student_id", "status"])


def downgrade() -> None:
    for t in ("wrong_record", "student_kp", "uploaded_question_kp", "platform_question_kp",
              "uploaded_question", "platform_question", "passage"):
        if _has(t):
            op.drop_table(t)
    op.execute("DROP TABLE IF EXISTS answer_log CASCADE")
