"""敏感操作二次审批(maker-checker):sensitive_approval 表。

高风险操作(退款批准/批量发券)超阈值 → 落 pending,由另一位管理员复核后执行。
幂等(IF NOT EXISTS)。

Revision ID: m141_sensitive_approval
Revises: m140_drop_kp_mastery_ledger
Create Date: 2026-07-10
"""
from alembic import op

revision = "m141_sensitive_approval"
down_revision = "m140_drop_kp_mastery_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS sensitive_approval (
            id           UUID PRIMARY KEY,
            action_type  VARCHAR(40) NOT NULL,
            summary      VARCHAR(300) NOT NULL,
            payload      JSONB NOT NULL,
            amount_fen   INTEGER,
            maker_id     UUID NOT NULL,
            maker_note   VARCHAR(500),
            status       VARCHAR(16) NOT NULL DEFAULT 'pending',
            checker_id   UUID,
            checker_note VARCHAR(500),
            exec_error   VARCHAR(500),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_at   TIMESTAMPTZ
        )
    """)
    # 待办列表按状态 + 时间查
    op.execute("CREATE INDEX IF NOT EXISTS ix_sensitive_approval_status "
               "ON sensitive_approval (status, created_at DESC)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS sensitive_approval")
