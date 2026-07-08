"""考点讲解新表 kp_lecture(按教学环节 section 结构化,取代 node_resource 六维)。

一考点一套讲解、一环节一行(node_id + section_key 唯一);draft/published 逐段发布。
旧 node_resource 六维讲解不兼容、不迁移(见 m138 清理)。幂等(IF NOT EXISTS)。

Revision ID: m137_kp_lecture
Revises: m136_curriculum_catalog
Create Date: 2026-07-07
"""
from alembic import op

revision = "m137_kp_lecture"
down_revision = "m136_curriculum_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS kp_lecture (
            id           UUID PRIMARY KEY,
            node_id      UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
            section_key  VARCHAR(32) NOT NULL,
            content_md   TEXT,
            media_url    VARCHAR,
            status       VARCHAR(16) NOT NULL DEFAULT 'draft',
            source       VARCHAR(16) NOT NULL DEFAULT 'manual',
            sort_order   INTEGER NOT NULL DEFAULT 0,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_kp_lecture_identity UNIQUE (node_id, section_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kp_lecture_node ON kp_lecture (node_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS kp_lecture")
