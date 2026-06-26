"""R10 re-base:语法掌握改挂规范受控树 knowledge_nodes。

- knowledge_nodes 加 grammar_probes_json(探针库缓存,原在 knowledge_points)。
- student_grammar_mastery.kp_id FK 由 knowledge_points 改指 knowledge_nodes;
  grammar_placement_session 清空(pool_kp_ids 存的是旧 knowledge_points id)。
  (掌握/会话均为演示数据,直接清空重来,不迁移。)

Revision ID: m118_grammar_on_nodes
Revises: m117_grammar_placement
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "m118_grammar_on_nodes"
down_revision = "m117_grammar_placement"
branch_labels = None
depends_on = None


def _cols(t):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(t)}


def upgrade():
    if "grammar_probes_json" not in _cols("knowledge_nodes"):
        op.add_column("knowledge_nodes", sa.Column("grammar_probes_json", JSONB(), nullable=True))

    # 清演示数据(旧 kp_id 指向 knowledge_points,re-base 后无意义)
    op.execute("DELETE FROM student_grammar_mastery")
    op.execute("DELETE FROM grammar_placement_session")

    # kp_id FK: knowledge_points → knowledge_nodes(自动发现旧约束名后替换)
    op.execute("""
    DO $$
    DECLARE c text;
    BEGIN
      SELECT tc.constraint_name INTO c
      FROM information_schema.table_constraints tc
      JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
      WHERE tc.table_name='student_grammar_mastery' AND tc.constraint_type='FOREIGN KEY'
        AND ccu.table_name='knowledge_points';
      IF c IS NOT NULL THEN EXECUTE 'ALTER TABLE student_grammar_mastery DROP CONSTRAINT '||quote_ident(c); END IF;
      ALTER TABLE student_grammar_mastery
        ADD CONSTRAINT fk_sgm_kp_node FOREIGN KEY (kp_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE;
    END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE student_grammar_mastery DROP CONSTRAINT IF EXISTS fk_sgm_kp_node")
    if "grammar_probes_json" in _cols("knowledge_nodes"):
        op.drop_column("knowledge_nodes", "grammar_probes_json")
