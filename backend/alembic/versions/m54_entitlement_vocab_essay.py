"""权益体系 + 词力通设置/发音日志 + 作文应试 表与列补迁移

本迁移把此前在沙箱中用裸 DDL 手建、未进 alembic 的对象正式纳入版本：
  新表:
    - student_vocab_settings   (词力通：每组词数/重复/错词结转阈值)
    - vocab_pron_logs          (词力通发音评测日志)
    - essay_prompts            (应试写作题库)
    - essay_error_log          (写作错因本)
    - feature_overrides        (权益：运营覆盖 key+tier)
    - feature_usage            (权益：周期用量计数)
    - feature_addon_config     (权益：功能加量包配置)
    - feature_addon_balance    (权益：用户加量包余额)
  新列:
    - orders.addon_feature_key
    - study_checkins.wrong_count
    - student_vocab_settings.wrong_carry_threshold (随建表一并创建)

为兼容「全新生产库」与「已手建的开发库」，每个对象创建前做存在性检查，
已存在则跳过，使两类库都能安全 `alembic upgrade head`。

Revision ID: m54_entitlement_vocab_essay
Revises: m53_vocab_phrases
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m54_entitlement_vocab_essay"
down_revision = "m53_vocab_phrases"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names()


def _has_column(table: str, col: str) -> bool:
    if not _has_table(table):
        return False
    return col in {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    # ---- student_vocab_settings ----
    if not _has_table("student_vocab_settings"):
        op.create_table(
            "student_vocab_settings",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("words_per_group", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("reps_per_group", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("wrong_carry_threshold", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "uix_student_vocab_settings_student",
            "student_vocab_settings", ["student_id"], unique=True,
        )
    elif not _has_column("student_vocab_settings", "wrong_carry_threshold"):
        op.add_column(
            "student_vocab_settings",
            sa.Column("wrong_carry_threshold", sa.Integer(), nullable=False, server_default="2"),
        )

    # ---- vocab_pron_logs ----
    if not _has_table("vocab_pron_logs"):
        op.create_table(
            "vocab_pron_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("reference_text", sa.String(), nullable=False),
            sa.Column("word_id", UUID(as_uuid=True), nullable=True),
            sa.Column("overall", sa.SmallInteger(), nullable=False),
            sa.Column("accuracy", sa.SmallInteger(), nullable=True),
            sa.Column("fluency", sa.SmallInteger(), nullable=True),
            sa.Column("completion", sa.SmallInteger(), nullable=True),
            sa.Column("weak", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "ix_vocab_pron_logs_student",
            "vocab_pron_logs", ["student_id", "created_at"],
        )

    # ---- essay_prompts ----
    if not _has_table("essay_prompts"):
        op.create_table(
            "essay_prompts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("stage", sa.String(), nullable=False),
            sa.Column("genre", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("scenario", sa.Text(), nullable=False),
            sa.Column("required_points", JSONB(), nullable=False),
            sa.Column("person", sa.String(), nullable=True),
            sa.Column("tense", sa.String(), nullable=True),
            sa.Column("word_min", sa.SmallInteger(), nullable=True),
            sa.Column("word_max", sa.SmallInteger(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="admin"),
            sa.Column("parent_prompt_id", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "ix_essay_prompts_stage_genre",
            "essay_prompts", ["stage", "genre"],
        )

    # ---- essay_error_log ----
    if not _has_table("essay_error_log"):
        op.create_table(
            "essay_error_log",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", UUID(as_uuid=True), nullable=False),
            sa.Column("essay_id", UUID(as_uuid=True), nullable=True),
            sa.Column("type", sa.String(), nullable=False),
            sa.Column("original", sa.Text(), nullable=True),
            sa.Column("suggestion", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "ix_essay_error_log_student",
            "essay_error_log", ["student_id", "created_at"],
        )

    # ---- feature_overrides ----
    if not _has_table("feature_overrides"):
        op.create_table(
            "feature_overrides",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("feature_key", sa.String(), nullable=False),
            sa.Column("tier", sa.String(), nullable=False),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("quota_limit", sa.Integer(), nullable=True),
            sa.Column("quota_period", sa.String(), nullable=True),
            sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "uix_feature_overrides_key_tier",
            "feature_overrides", ["feature_key", "tier"], unique=True,
        )

    # ---- feature_usage ----
    if not _has_table("feature_usage"):
        op.create_table(
            "feature_usage",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("feature_key", sa.String(), nullable=False),
            sa.Column("period_bucket", sa.String(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "uix_feature_usage",
            "feature_usage", ["user_id", "feature_key", "period_bucket"], unique=True,
        )

    # ---- feature_addon_config (PK = feature_key) ----
    if not _has_table("feature_addon_config"):
        op.create_table(
            "feature_addon_config",
            sa.Column("feature_key", sa.String(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("pack_size", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("price_fen", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )

    # ---- feature_addon_balance ----
    if not _has_table("feature_addon_balance"):
        op.create_table(
            "feature_addon_balance",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), nullable=False),
            sa.Column("feature_key", sa.String(), nullable=False),
            sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        )
        op.create_index(
            "uix_feature_addon_balance",
            "feature_addon_balance", ["user_id", "feature_key"], unique=True,
        )

    # ---- 现有表新增列 ----
    if not _has_column("orders", "addon_feature_key"):
        op.add_column("orders", sa.Column("addon_feature_key", sa.String(), nullable=True))

    if not _has_column("study_checkins", "wrong_count"):
        op.add_column(
            "study_checkins",
            sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("study_checkins", "wrong_count"):
        op.drop_column("study_checkins", "wrong_count")
    if _has_column("orders", "addon_feature_key"):
        op.drop_column("orders", "addon_feature_key")

    for tbl in (
        "feature_addon_balance",
        "feature_addon_config",
        "feature_usage",
        "feature_overrides",
        "essay_error_log",
        "essay_prompts",
        "vocab_pron_logs",
        "student_vocab_settings",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
