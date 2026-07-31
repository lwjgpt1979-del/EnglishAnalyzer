"""m217: 单元 course_text + 理解向长难句清单/缓存.

Revision ID: m217_unit_ls_understand
Revises: m208_kp_title_rewrite_cache
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "m217_unit_ls_understand"
down_revision = "m208_kp_title_rewrite_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 粘贴原文(找出/合成长难句输入)
    op.execute(
        "ALTER TABLE curriculum_units ADD COLUMN IF NOT EXISTS course_text TEXT"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS unit_understand_ls ("
        "id UUID PRIMARY KEY, "
        "unit_id UUID NOT NULL, "
        "text TEXT NOT NULL, "
        "translation TEXT, "
        "why TEXT, "
        "src VARCHAR(12) NOT NULL, "
        "difficulty INTEGER, "
        "sort_order INTEGER NOT NULL DEFAULT 0, "
        "course_text_md5 VARCHAR(32), "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_unit_understand_ls_unit "
        "ON unit_understand_ls (unit_id, sort_order)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS unit_ls_understand_cache ("
        "input_md5 VARCHAR(32) PRIMARY KEY, "
        "unit_id UUID, "
        "grade VARCHAR(32), "
        "result JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS unit_ls_understand_cache")
    op.execute("DROP TABLE IF EXISTS unit_understand_ls")
    op.execute("ALTER TABLE curriculum_units DROP COLUMN IF EXISTS course_text")
