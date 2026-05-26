"""add ocr_status to wrong_questions

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-27
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "3c7d8e2f1a04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ocr_status_enum already exists from initial migration (used by ocr_tasks)
    op.add_column(
        "wrong_questions",
        sa.Column(
            "ocr_status",
            sa.Enum(
                "pending", "processing", "completed", "failed",
                name="ocr_status",
                create_type=False,   # enum type already exists
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("wrong_questions", "ocr_status")
