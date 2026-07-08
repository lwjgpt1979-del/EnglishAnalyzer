"""教材主数据表 curriculum_catalog(版本/年级/学期 唯一真源 + 上下架)。

全站版本/年级/学期可选项、学生内容可见性均以本表为准(见 CLAUDE.md「主数据上架/下架」铁律)。
可先建版本(内容后补);上架粒度=版本+年级+学期。存量:从 curriculum_units 回填每个
(版本,年级,学期)组合,该组合有 published 单元→上架(published),否则下架(draft),保持既有可见性。
幂等(IF NOT EXISTS)。

Revision ID: m136_curriculum_catalog
Revises: m135_curriculum_unit_status
Create Date: 2026-07-07
"""
from alembic import op

revision = "m136_curriculum_catalog"
down_revision = "m135_curriculum_unit_status"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_catalog (
            id UUID PRIMARY KEY,
            textbook_version VARCHAR NOT NULL,
            grade VARCHAR NOT NULL,
            semester VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'draft',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uix_curriculum_catalog_identity
                UNIQUE (textbook_version, grade, semester)
        )
    """)
    # 存量回填:每个 (版本,年级,学期) 组合各一行;组合内有 published 单元→上架,否则下架。
    op.execute("""
        INSERT INTO curriculum_catalog (id, textbook_version, grade, semester, status)
        SELECT gen_random_uuid(), textbook_version, grade, semester::varchar,
               CASE WHEN bool_or(status = 'published') THEN 'published' ELSE 'draft' END
        FROM curriculum_units
        GROUP BY textbook_version, grade, semester::varchar
        ON CONFLICT (textbook_version, grade, semester) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS curriculum_catalog")
