"""initial_schema

Revision ID: 9f9152b49be9
Revises:
Create Date: 2026-05-25 23:31:09.071640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9f9152b49be9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ENUM types ─────────────────────────────────────────────────────────
    # Create all PostgreSQL native ENUM types before any table that uses them.
    # Using CHECKFIRST=True so re-running is safe.

    user_role = postgresql.ENUM(
        "student", "teacher", "relative",
        "institution_admin", "branch_admin", "platform_admin",
        name="user_role", create_type=False,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    city_source = postgresql.ENUM("ip_auto", "manual", name="city_source", create_type=False)
    city_source.create(op.get_bind(), checkfirst=True)

    institution_status = postgresql.ENUM("pending", "active", "suspended", name="institution_status", create_type=False)
    institution_status.create(op.get_bind(), checkfirst=True)

    semester = postgresql.ENUM("上", "下", name="semester", create_type=False)
    semester.create(op.get_bind(), checkfirst=True)

    cert_status = postgresql.ENUM("uncertified", "pending", "certified", "rejected", name="cert_status", create_type=False)
    cert_status.create(op.get_bind(), checkfirst=True)

    bind_type = postgresql.ENUM("institution_assigned", "self_bound", name="bind_type", create_type=False)
    bind_type.create(op.get_bind(), checkfirst=True)

    bind_source = postgresql.ENUM("sms_invite", "miniprogram_link", "institution_assigned", name="bind_source", create_type=False)
    bind_source.create(op.get_bind(), checkfirst=True)

    teacher_student_status = postgresql.ENUM("pending", "active", "rejected", "inactive", name="teacher_student_status", create_type=False)
    teacher_student_status.create(op.get_bind(), checkfirst=True)

    invite_code_type = postgresql.ENUM("relative_bind", "institution_join", name="invite_code_type", create_type=False)
    invite_code_type.create(op.get_bind(), checkfirst=True)

    membership_tier = postgresql.ENUM("free", "basic", "pro", "promax", name="membership_tier", create_type=False)
    membership_tier.create(op.get_bind(), checkfirst=True)

    order_tier = postgresql.ENUM("basic", "pro", "promax", name="order_tier", create_type=False)
    order_tier.create(op.get_bind(), checkfirst=True)

    order_type = postgresql.ENUM("new", "renew", "upgrade", name="order_type", create_type=False)
    order_type.create(op.get_bind(), checkfirst=True)

    order_status = postgresql.ENUM("pending", "paid", "refunded", "partial_refunded", name="order_status", create_type=False)
    order_status.create(op.get_bind(), checkfirst=True)

    refund_type = postgresql.ENUM("standard_7d", "prorated", "appeal", name="refund_type", create_type=False)
    refund_type.create(op.get_bind(), checkfirst=True)

    refund_status = postgresql.ENUM("pending", "approved", "rejected", "completed", name="refund_status", create_type=False)
    refund_status.create(op.get_bind(), checkfirst=True)

    question_type = postgresql.ENUM("单选", "完型", "阅读", "作文", "其他", name="question_type", create_type=False)
    question_type.create(op.get_bind(), checkfirst=True)

    ocr_status = postgresql.ENUM("pending", "processing", "completed", "failed", name="ocr_status", create_type=False)
    ocr_status.create(op.get_bind(), checkfirst=True)

    ocr_provider = postgresql.ENUM("aliyun_print", "baidu_print", "tencent_handwrite", "google_handwrite", name="ocr_provider", create_type=False)
    ocr_provider.create(op.get_bind(), checkfirst=True)

    llm_provider = postgresql.ENUM("deepseek", "claude", name="llm_provider", create_type=False)
    llm_provider.create(op.get_bind(), checkfirst=True)

    knowledge_category = postgresql.ENUM("grammar", "vocabulary", "reading", "writing", "listening", name="knowledge_category", create_type=False)
    knowledge_category.create(op.get_bind(), checkfirst=True)

    vocab_level = postgresql.ENUM("new", "learning", "review", "mastered", name="vocab_level", create_type=False)
    vocab_level.create(op.get_bind(), checkfirst=True)

    essay_status = postgresql.ENUM("draft", "processing", "completed", name="essay_status", create_type=False)
    essay_status.create(op.get_bind(), checkfirst=True)

    listening_status = postgresql.ENUM("processing", "completed", "failed", name="listening_status", create_type=False)
    listening_status.create(op.get_bind(), checkfirst=True)

    ai_question_type = postgresql.ENUM("单选", "填空", "完型", "阅读", "写作", name="ai_question_type", create_type=False)
    ai_question_type.create(op.get_bind(), checkfirst=True)

    trigger_type = postgresql.ENUM("module8_free", "wrong_q_followup", name="trigger_type", create_type=False)
    trigger_type.create(op.get_bind(), checkfirst=True)

    assignment_status = postgresql.ENUM("draft", "published", "closed", name="assignment_status", create_type=False)
    assignment_status.create(op.get_bind(), checkfirst=True)

    report_type = postgresql.ENUM("weekly", "monthly", name="report_type", create_type=False)
    report_type.create(op.get_bind(), checkfirst=True)

    notification_type = postgresql.ENUM(
        "system", "membership", "assignment", "analysis_done", "report_ready",
        "bind_request", "bind_accepted", "bind_rejected", "ocr_failed",
        name="notification_type", create_type=False,
    )
    notification_type.create(op.get_bind(), checkfirst=True)

    settlement_status = postgresql.ENUM("draft", "confirmed", "paid", name="settlement_status", create_type=False)
    settlement_status.create(op.get_bind(), checkfirst=True)

    # ── Tables (dependency order) ───────────────────────────────────────────

    # 域1 — no-dep roots
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("openid", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("nickname", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("role", sa.Enum("student","teacher","relative","institution_admin","branch_admin","platform_admin", name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("city_code", sa.String(), nullable=True),
        sa.Column("city_source", sa.Enum("ip_auto","manual", name="city_source", create_type=False), nullable=True),
        sa.Column("ip_at_registration", postgresql.INET(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("openid"),
    )

    op.create_table(
        "branch_companies",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("manager_user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("legal_name", sa.String(), nullable=True),
        sa.Column("tax_number", sa.String(), nullable=True),
        sa.Column("bank_name", sa.String(), nullable=True),
        sa.Column("bank_account", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "institutions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact_phone", sa.String(), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("province_code", sa.String(), nullable=False),
        sa.Column("city_code", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("status", sa.Enum("pending","active","suspended", name="institution_status", create_type=False), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.Enum("grammar","vocabulary","reading","writing","listening", name="knowledge_category", create_type=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applicable_grades", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("applicable_textbooks", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("parent_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "vocabulary_words",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("word", sa.String(), nullable=False),
        sa.Column("phonetic", sa.String(), nullable=True),
        sa.Column("definitions", postgresql.JSONB(), nullable=False),
        sa.Column("examples", postgresql.JSONB(), nullable=True),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
    )

    # Depends on users + institutions
    op.create_table(
        "students",
        sa.Column("id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("institution_id", sa.UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("grade", sa.String(), nullable=True),
        sa.Column("textbook_ver", sa.String(), nullable=True),
        sa.Column("semester", sa.Enum("上","下", name="semester", create_type=False), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "teachers",
        sa.Column("id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("institution_id", sa.UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("cert_status", sa.Enum("uncertified","pending","certified","rejected", name="cert_status", create_type=False), server_default=sa.text("'uncertified'"), nullable=False),
        sa.Column("cert_doc_url", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("max_students", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("enterprise_userid", sa.String(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "relatives",
        sa.Column("id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    )

    op.create_table(
        "student_relatives",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("relative_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("bound_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("unbound_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("type", sa.Enum("relative_bind","institution_join", name="invite_code_type", create_type=False), nullable=False),
        sa.Column("issuer_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "teacher_students",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("teacher_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bind_type", sa.Enum("institution_assigned","self_bound", name="bind_type", create_type=False), nullable=False),
        sa.Column("bind_source", sa.Enum("sms_invite","miniprogram_link","institution_assigned", name="bind_source", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("pending","active","rejected","inactive", name="teacher_student_status", create_type=False), nullable=False),
        sa.Column("institution_id", sa.UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("bound_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("unbound_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 域2 — payments
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_no", sa.String(), nullable=False),
        sa.Column("payer_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("beneficiary_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_type", sa.Enum("new","renew","upgrade", name="order_type", create_type=False), nullable=False),
        sa.Column("tier", sa.Enum("basic","pro","promax", name="order_tier", create_type=False), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending","paid","refunded","partial_refunded", name="order_status", create_type=False), nullable=False),
        sa.Column("wx_transaction_id", sa.String(), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("branch_company_id", sa.UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True),
        sa.Column("platform_income_fen", sa.Integer(), nullable=True),
        sa.Column("branch_commission_fen", sa.Integer(), nullable=True),
        sa.Column("institution_commission_fen", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("order_no"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("tier", sa.Enum("free","basic","pro","promax", name="membership_tier", create_type=False), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "refund_records",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", sa.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        sa.Column("refund_type", sa.Enum("standard_7d","prorated","appeal", name="refund_type", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("pending","approved","rejected","completed", name="refund_status", create_type=False), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("wx_refund_id", sa.String(), nullable=True),
        sa.Column("branch_company_id", sa.UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=True),
        sa.Column("reviewed_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 域3 — wrong questions
    op.create_table(
        "wrong_questions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("institution_id", sa.UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("source_image_url", sa.String(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("student_answer", sa.Text(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("question_type", sa.Enum("单选","完型","阅读","作文","其他", name="question_type", create_type=False), nullable=True),
        sa.Column("difficulty", sa.SmallInteger(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("is_mastered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mastered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "ocr_tasks",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("wrong_question_id", sa.UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False),
        sa.Column("status", sa.Enum("pending","processing","completed","failed", name="ocr_status", create_type=False), nullable=False),
        sa.Column("provider", sa.Enum("aliyun_print","baidu_print","tencent_handwrite","google_handwrite", name="ocr_provider", create_type=False), nullable=True),
        sa.Column("raw_result", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("wrong_question_id", sa.UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=False),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("llm_provider", sa.Enum("deepseek","claude", name="llm_provider", create_type=False), nullable=False),
        sa.Column("error_types", postgresql.JSONB(), nullable=False),
        sa.Column("knowledge_points", postgresql.JSONB(), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("suggestions", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 域4 — knowledge
    op.create_table(
        "curriculum_units",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("textbook_version", sa.String(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column("semester", sa.Enum("上","下", name="semester", create_type=False), nullable=False),
        sa.Column("unit_no", sa.Integer(), nullable=False),
        sa.Column("unit_title", sa.String(), nullable=False),
        sa.UniqueConstraint("textbook_version", "grade", "semester", "unit_no", name="uix_curriculum_units_identity"),
    )

    op.create_table(
        "unit_knowledge_points",
        sa.Column("unit_id", sa.UUID(as_uuid=True), sa.ForeignKey("curriculum_units.id"), primary_key=True),
        sa.Column("knowledge_point_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
    )

    op.create_table(
        "curriculum_words",
        sa.Column("unit_id", sa.UUID(as_uuid=True), sa.ForeignKey("curriculum_units.id"), primary_key=True),
        sa.Column("word_id", sa.UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), primary_key=True),
        sa.Column("is_core", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    op.create_table(
        "wrong_question_knowledge_points",
        sa.Column("wrong_question_id", sa.UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), primary_key=True),
        sa.Column("knowledge_point_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), primary_key=True),
    )

    # 域5 — learning
    op.create_table(
        "vocabulary_learning",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), sa.ForeignKey("vocabulary_words.id"), nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("repetitions", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("easiness_factor", sa.Numeric(4, 2), server_default=sa.text("2.5"), nullable=False),
        sa.Column("next_review_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("level", sa.Enum("new","learning","review","mastered", name="vocab_level", create_type=False), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "word_id", name="uix_vocabulary_learning_student_word"),
    )

    op.create_table(
        "essays",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("wrong_question_id", sa.UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("polished_text", sa.Text(), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(), nullable=True),
        sa.Column("round_count", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Enum("draft","processing","completed", name="essay_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "listening_records",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("audio_url", sa.String(), nullable=False),
        sa.Column("reference_url", sa.String(), nullable=False),
        sa.Column("status", sa.Enum("processing","completed","failed", name="listening_status", create_type=False), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("feedback", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "study_checkins",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.Column("new_words_count", sa.Integer(), nullable=False),
        sa.Column("review_done", sa.Boolean(), nullable=False),
        sa.Column("streak_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "checkin_date", name="uix_study_checkins_student_date"),
    )

    # 域6 — AI questions
    op.create_table(
        "ai_questions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_point_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("unit_id", sa.UUID(as_uuid=True), sa.ForeignKey("curriculum_units.id"), nullable=True),
        sa.Column("question_type", sa.Enum("单选","填空","完型","阅读","写作", name="ai_question_type", create_type=False), nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "practice_records",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_id", sa.UUID(as_uuid=True), sa.ForeignKey("ai_questions.id"), nullable=False),
        sa.Column("trigger_type", sa.Enum("module8_free","wrong_q_followup", name="trigger_type", create_type=False), nullable=False),
        sa.Column("student_answer", postgresql.JSONB(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("wrong_question_id", sa.UUID(as_uuid=True), sa.ForeignKey("wrong_questions.id"), nullable=True),
        sa.Column("practiced_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("time_spent_sec", sa.Integer(), nullable=True),
    )

    # 域7 — teacher
    op.create_table(
        "classes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("teacher_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("institution_id", sa.UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "class_students",
        sa.Column("class_id", sa.UUID(as_uuid=True), sa.ForeignKey("classes.id"), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("teacher_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_id", sa.UUID(as_uuid=True), sa.ForeignKey("classes.id"), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=True),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("draft","published","closed", name="assignment_status", create_type=False), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "assignment_submissions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", sa.UUID(as_uuid=True), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assignment_id", "student_id", name="uix_assignment_submissions_unique"),
    )

    # 域8 — usage
    op.create_table(
        "daily_usage",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("usage_type", sa.String(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.UniqueConstraint("user_id", "usage_type", "period", name="uix_daily_usage_identity"),
    )

    op.create_table(
        "learning_report_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_type", sa.Enum("weekly","monthly", name="report_type", create_type=False), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report_data", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id", "report_type", "period_start", name="uix_learning_report_identity"),
    )

    # 域9 — system
    op.create_table(
        "system_configs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Enum("system","membership","assignment","analysis_done","report_ready","bind_request","bind_accepted","bind_rejected","ocr_failed", name="notification_type", create_type=False), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 域10 — branch
    op.create_table(
        "branch_company_cities",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("branch_company_id", sa.UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False),
        sa.Column("city_code", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "branch_settlements",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("branch_company_id", sa.UUID(as_uuid=True), sa.ForeignKey("branch_companies.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("gross_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("refund_deduction_fen", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("net_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("platform_share_fen", sa.Integer(), nullable=False),
        sa.Column("branch_payable_fen", sa.Integer(), nullable=False),
        sa.Column("commission_rate_snapshot", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.Enum("draft","confirmed","paid", name="settlement_status", create_type=False), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("branch_company_id", "period_start", "period_end", name="uix_branch_settlements_period"),
    )

    # ── Partial unique indexes (PostgreSQL-specific, created after tables) ──
    op.create_index(
        "uix_teacher_students_active",
        "teacher_students",
        ["teacher_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uix_memberships_user_active",
        "memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "uix_branch_company_cities_active_city",
        "branch_company_cities",
        ["city_code"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )


def downgrade() -> None:
    # Drop partial indexes first
    op.drop_index("uix_branch_company_cities_active_city", table_name="branch_company_cities")
    op.drop_index("uix_memberships_user_active", table_name="memberships")
    op.drop_index("uix_teacher_students_active", table_name="teacher_students")

    # Drop tables in reverse dependency order
    op.drop_table("branch_settlements")
    op.drop_table("branch_company_cities")
    op.drop_table("notifications")
    op.drop_table("system_configs")
    op.drop_table("learning_report_snapshots")
    op.drop_table("daily_usage")
    op.drop_table("assignment_submissions")
    op.drop_table("assignments")
    op.drop_table("class_students")
    op.drop_table("classes")
    op.drop_table("practice_records")
    op.drop_table("ai_questions")
    op.drop_table("study_checkins")
    op.drop_table("listening_records")
    op.drop_table("essays")
    op.drop_table("vocabulary_learning")
    op.drop_table("wrong_question_knowledge_points")
    op.drop_table("curriculum_words")
    op.drop_table("unit_knowledge_points")
    op.drop_table("curriculum_units")
    op.drop_table("ai_analyses")
    op.drop_table("ocr_tasks")
    op.drop_table("wrong_questions")
    op.drop_table("refund_records")
    op.drop_table("memberships")
    op.drop_table("orders")
    op.drop_table("teacher_students")
    op.drop_table("invite_codes")
    op.drop_table("student_relatives")
    op.drop_table("relatives")
    op.drop_table("teachers")
    op.drop_table("students")
    op.drop_table("vocabulary_words")
    op.drop_table("knowledge_points")
    op.drop_table("institutions")
    op.drop_table("branch_companies")
    op.drop_table("users")

    # Drop ENUM types
    for enum_name in [
        "settlement_status", "notification_type", "report_type",
        "assignment_status", "trigger_type", "ai_question_type",
        "listening_status", "essay_status", "vocab_level",
        "knowledge_category", "llm_provider", "ocr_provider",
        "ocr_status", "question_type", "refund_status", "refund_type",
        "order_status", "order_type", "order_tier", "membership_tier",
        "invite_code_type", "teacher_student_status", "bind_source",
        "bind_type", "cert_status", "semester", "institution_status",
        "city_source", "user_role",
    ]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
