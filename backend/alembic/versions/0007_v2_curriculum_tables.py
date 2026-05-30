"""v2_curriculum_tables: 9 V2 core tables (M1 / D-079)

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create new enum types explicitly via raw SQL
    op.execute("CREATE TYPE content_dimension AS ENUM ('listening', 'dictation', 'grammar', 'writing')")
    op.execute("CREATE TYPE content_status AS ENUM ('draft', 'reviewing', 'published', 'retired')")
    op.execute("CREATE TYPE content_generated_by AS ENUM ('ai_full', 'ai_with_human_review')")
    op.execute("CREATE TYPE exam_source AS ENUM ('official_seed', 'teacher_upload')")
    op.execute("CREATE TYPE exam_status AS ENUM ('draft', 'published', 'retired')")
    op.execute("CREATE TYPE sim_status AS ENUM ('draft', 'reviewing', 'published', 'retired')")

    # Use sa.Text for enum columns to avoid SQLAlchemy type-registry interference.
    # The actual column type in the DB is enforced by the CAST in the column type
    # or kept as the named enum via PostgreSQL DDL above. We use sa.Text here
    # for the migration only; SQLAlchemy ORM models use the proper Enum types.
    # Use sa.Enum(..., create_type=False) with metadata=sa.MetaData() to isolate from app metadata.
    meta = sa.MetaData()

    def _new_enum(*args, name):
        return sa.Enum(*args, name=name, create_type=False, metadata=meta)

    def _existing_enum(name):
        return sa.Enum(name=name, create_type=False, metadata=meta)

    # —— knowledge_point_contents ——
    op.create_table(
        "knowledge_point_contents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("dimension", _new_enum("listening", "dictation", "grammar", "writing", name="content_dimension"), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("audio_url", sa.String, nullable=True),
        sa.Column("example_json", JSONB, nullable=True),
        sa.Column("status", _new_enum("draft", "reviewing", "published", "retired", name="content_status"), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("generated_by", _new_enum("ai_full", "ai_with_human_review", name="content_generated_by"), nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("knowledge_point_id", "dimension", name="uix_kp_dimension"),
    )

    # —— exam_papers ——
    op.create_table(
        "exam_papers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", _new_enum("official_seed", "teacher_upload", name="exam_source"), nullable=False),
        sa.Column("uploader_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("class_id", UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True),
        sa.Column("textbook_version", sa.String, nullable=False),
        sa.Column("grade", sa.String, nullable=False),
        sa.Column("semester", _existing_enum("semester"), nullable=False),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("paper_url", sa.String, nullable=True),
        sa.Column("ocr_status", sa.String, nullable=True),
        sa.Column("status", _new_enum("draft", "published", "retired", name="exam_status"), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— exam_questions ——
    op.create_table(
        "exam_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("exam_papers.id"), nullable=False),
        sa.Column("question_no", sa.String, nullable=False),
        sa.Column("question_type", _existing_enum("ai_question_type"), nullable=False),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("difficulty", sa.SmallInteger, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— exam_question_knowledge_points ——
    op.create_table(
        "exam_question_knowledge_points",
        sa.Column("exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
        sa.Column("relevance", sa.SmallInteger, nullable=False, server_default=sa.text("100")),
    )

    # —— simulated_questions ——
    op.create_table(
        "simulated_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("question_type", _existing_enum("ai_question_type"), nullable=False),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("difficulty", sa.SmallInteger, nullable=False),
        sa.Column("generation_metadata", JSONB, nullable=True),
        sa.Column("status", _new_enum("draft", "reviewing", "published", "retired", name="sim_status"), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_uploaded_papers ——
    op.create_table(
        "user_uploaded_papers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("source_image_urls", JSONB, nullable=False),
        sa.Column("ocr_status", sa.String, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_paper_questions ——
    op.create_table(
        "user_paper_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_paper_id", UUID(as_uuid=True), sa.ForeignKey("user_uploaded_papers.id"), nullable=False),
        sa.Column("question_no", sa.String, nullable=True),
        sa.Column("question_type", _existing_enum("ai_question_type"), nullable=True),
        sa.Column("stem", sa.Text, nullable=True),
        sa.Column("student_answer", sa.Text, nullable=True),
        sa.Column("correct_answer", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("is_wrong", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("matched_exam_question_id", UUID(as_uuid=True), sa.ForeignKey("exam_questions.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # —— user_paper_question_knowledge_points ——
    op.create_table(
        "user_paper_question_knowledge_points",
        sa.Column("user_paper_question_id", UUID(as_uuid=True), sa.ForeignKey("user_paper_questions.id"), primary_key=True),
        sa.Column("knowledge_point_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
    )

    # —— purchased_semesters ——
    op.create_table(
        "purchased_semesters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("textbook_version", sa.String, nullable=False),
        sa.Column("grade", sa.String, nullable=False),
        sa.Column("semester", _existing_enum("semester"), nullable=False),
        sa.Column("tier", _existing_enum("order_tier"), nullable=False),
        sa.Column("semester_no", sa.SmallInteger, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_purchased_semesters_user_lookup",
        "purchased_semesters",
        ["user_id", "textbook_version", "grade", "semester"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchased_semesters_user_lookup", table_name="purchased_semesters")
    op.drop_table("purchased_semesters")
    op.drop_table("user_paper_question_knowledge_points")
    op.drop_table("user_paper_questions")
    op.drop_table("user_uploaded_papers")
    op.drop_table("simulated_questions")
    op.drop_table("exam_question_knowledge_points")
    op.drop_table("exam_questions")
    op.drop_table("exam_papers")
    op.drop_table("knowledge_point_contents")
    for t in ["content_dimension", "content_status", "content_generated_by",
              "exam_source", "exam_status", "sim_status"]:
        op.execute(f"DROP TYPE {t}")
