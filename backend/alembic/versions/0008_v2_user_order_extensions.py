"""v2_user_order_extensions: users +preferred_*; orders +semester_count, purchased_semester_ids; system_configs seed pricing

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import json
import uuid

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— users +preferred_* ——
    op.add_column("users", sa.Column("preferred_textbook_version", sa.String, nullable=True))
    op.add_column("users", sa.Column("preferred_grade", sa.String, nullable=True))
    op.add_column("users", sa.Column("preferred_semester", sa.Enum(name="semester", create_type=False), nullable=True))

    # —— orders +V2 ——
    op.add_column("orders", sa.Column("semester_count", sa.SmallInteger, nullable=True))
    op.add_column("orders", sa.Column("purchased_semester_ids", JSONB, nullable=True))

    # —— system_configs 插入价格种子 ——
    conn = op.get_bind()
    admin = conn.execute(sa.text(
        "SELECT id FROM users WHERE role='platform_admin' ORDER BY created_at LIMIT 1"
    )).fetchone()
    if not admin:
        admin = conn.execute(sa.text(
            "SELECT id FROM users ORDER BY created_at LIMIT 1"
        )).fetchone()
    if admin:
        conn.execute(sa.text("""
            INSERT INTO system_configs (id, key, value, description, updated_by, created_at, updated_at)
            VALUES (:id, 'semester_pricing', CAST(:val AS jsonb), '学期会员定价（单位：元/学期）', :admin, now(), now())
            ON CONFLICT (key) DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "val": json.dumps({"basic": 39, "pro": 79, "promax": 159}),
            "admin": str(admin[0]),
        })


def downgrade() -> None:
    op.execute("DELETE FROM system_configs WHERE key='semester_pricing'")
    op.drop_column("orders", "purchased_semester_ids")
    op.drop_column("orders", "semester_count")
    op.drop_column("users", "preferred_semester")
    op.drop_column("users", "preferred_grade")
    op.drop_column("users", "preferred_textbook_version")
