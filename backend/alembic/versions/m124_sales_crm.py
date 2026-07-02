"""域23 电销 CRM:sales_lead + sales_lead_activity。幂等。

Revision ID: m124_sales_crm
Revises: m123_paper_year
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "m124_sales_crm"
down_revision = "m123_paper_year"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "sales_lead" not in tables:
        op.create_table(
            "sales_lead",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("contact_name", sa.String(80), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("wechat_id", sa.String(128), nullable=True),
            sa.Column("address", sa.String(255), nullable=True),
            sa.Column("region_code", sa.String(12), nullable=True),
            sa.Column("region_name", sa.String(64), nullable=True),
            sa.Column("industry", sa.String(64), nullable=True),
            sa.Column("biz_tags", JSONB, nullable=True),
            sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'manual'")),
            sa.Column("source_note", sa.String(255), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'new'")),
            sa.Column("intent_score", sa.Integer, nullable=True),
            sa.Column("intent_grade", sa.String(2), nullable=True),
            sa.Column("product_feedback", JSONB, nullable=True),
            sa.Column("similar_score", sa.Float, nullable=True),
            sa.Column("consent", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("dnc", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("pool", sa.String(8), nullable=False, server_default=sa.text("'public'")),
            sa.Column("owner_admin_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("claimed_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("last_contacted_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("next_follow_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("institution_id", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_sales_lead_pool_status", "sales_lead", ["pool", "status"])
        op.create_index("ix_sales_lead_owner", "sales_lead", ["owner_admin_id"])
        op.create_index("ix_sales_lead_region", "sales_lead", ["region_code"])
        op.create_index("ix_sales_lead_next_follow", "sales_lead", ["next_follow_at"])
        op.create_index("ix_sales_lead_phone", "sales_lead", ["phone"])

    if "sales_lead_activity" not in tables:
        op.create_table(
            "sales_lead_activity",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("lead_id", UUID(as_uuid=True),
                      sa.ForeignKey("sales_lead.id", ondelete="CASCADE"), nullable=False),
            sa.Column("admin_id", UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("channel", sa.String(8), nullable=False),
            sa.Column("direction", sa.String(4), nullable=True),
            sa.Column("content", sa.Text, nullable=True),
            sa.Column("outcome", sa.String(16), nullable=True),
            sa.Column("recording_url", sa.String(512), nullable=True),
            sa.Column("call_duration_sec", sa.Integer, nullable=True),
            sa.Column("asr_text", sa.Text, nullable=True),
            sa.Column("intent_score", sa.Integer, nullable=True),
            sa.Column("analysis", JSONB, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_sales_activity_lead", "sales_lead_activity", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_table("sales_lead_activity")
    op.drop_table("sales_lead")
