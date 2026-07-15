"""wrong_record 加冗余题面(统一错题中枢自洽)。幂等。

Revision ID: m164_wrong_record_denorm
Revises: m163_upq_kp_key
Create Date: 2026-07-15
"""
from alembic import op

revision = "m164_wrong_record_denorm"
down_revision = "m163_upq_kp_key"
branch_labels = None
depends_on = None

_COLS = [("stem","TEXT"),("student_answer","TEXT"),("correct_answer","TEXT"),
         ("explanation","TEXT"),("question_type","VARCHAR(24)"),
         ("kp_kind","VARCHAR(12)"),("kp_name","VARCHAR(120)"),("source_label","VARCHAR(16)")]

def upgrade():
    for c,t in _COLS:
        op.execute(f"ALTER TABLE wrong_record ADD COLUMN IF NOT EXISTS {c} {t}")

def downgrade():
    for c,_ in _COLS:
        op.execute(f"ALTER TABLE wrong_record DROP COLUMN IF EXISTS {c}")
