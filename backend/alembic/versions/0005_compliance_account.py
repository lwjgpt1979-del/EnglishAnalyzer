"""compliance: age verification + agreement + account cancellation

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birth_year", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("guardian_phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("guardian_verified_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("agreement_version", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("agreement_agreed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("profile_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("minor_purchase_consent_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivation_requested_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivation_scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("is_anonymized", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("phone_verify_code", sa.String(length=6), nullable=True))
    op.add_column("users", sa.Column("phone_verify_purpose", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("phone_verify_target", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("phone_verify_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    for col in [
        "phone_verify_expires_at", "phone_verify_target", "phone_verify_purpose", "phone_verify_code",
        "is_anonymized", "deactivation_scheduled_at", "deactivation_requested_at",
        "minor_purchase_consent_at", "profile_completed",
        "agreement_agreed_at", "agreement_version",
        "guardian_verified_at", "guardian_phone", "birth_year",
    ]:
        op.drop_column("users", col)
