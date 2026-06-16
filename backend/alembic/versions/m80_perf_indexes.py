"""性能索引补齐（上线硬化）：热点表缺失索引

静态审计发现 orders 仅有 order_no/pkey，但被大盘(GMV/ARPU/续费/漏斗)、
订单列表、优惠券/活动限购等高频按 payer/beneficiary/status/paid_at/promo 过滤；
另补 assignments/teacher_students/user_paper_questions/refund_records 的热点/FK 索引。
全部带存在性保护，可重复 upgrade head。

Revision ID: m80_perf_indexes
Revises: m79_rate_limits
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "m80_perf_indexes"
down_revision = "m79_rate_limits"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_index(table: str, name: str) -> bool:
    try:
        return name in {i["name"] for i in _insp().get_indexes(table)}
    except Exception:
        return False


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


# (index_name, table, columns, postgresql_where)
_INDEXES = [
    ("ix_orders_beneficiary", "orders", ["beneficiary_id"], None),
    ("ix_orders_payer", "orders", ["payer_id"], None),
    ("ix_orders_status_paid", "orders", ["status", "paid_at"], None),
    ("ix_orders_promo", "orders", ["promo_campaign_id"], "promo_campaign_id IS NOT NULL"),
    ("ix_assignments_teacher", "assignments", ["teacher_id", "created_at"], None),
    ("ix_teacher_students_student", "teacher_students", ["student_id"], None),
    ("ix_user_paper_questions_paper", "user_paper_questions", ["user_paper_id"], None),
    ("ix_refund_records_order", "refund_records", ["order_id"], None),
]


def upgrade() -> None:
    for name, table, cols, where in _INDEXES:
        if _has_table(table) and not _has_index(table, name):
            kw = {"postgresql_where": sa.text(where)} if where else {}
            op.create_index(name, table, cols, **kw)


def downgrade() -> None:
    for name, table, _cols, _w in _INDEXES:
        if _has_table(table) and _has_index(table, name):
            op.drop_index(name, table_name=table)
