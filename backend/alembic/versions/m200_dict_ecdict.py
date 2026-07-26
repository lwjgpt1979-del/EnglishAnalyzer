"""英汉词典参考表 dict_ecdict(ECDICT·MIT):补 vocab 释义/音标缺口的数据源。

数据每环境由导入脚本从 ecdict.csv 灌入(不进 content_seed,免把 66MB 塞进生产种子)。
用于:① 存量空释义词回填 ② 运行时「查看即生成」dict-first + LLM 兜底。幂等。

Revision ID: m200_dict_ecdict
Revises: m199_merge_heads
Create Date: 2026-07-26
"""
from alembic import op

revision = "m200_dict_ecdict"
down_revision = "m199_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS dict_ecdict (
            id          BIGSERIAL PRIMARY KEY,
            word        VARCHAR(128) NOT NULL,
            word_lower  VARCHAR(128) NOT NULL,
            phonetic    VARCHAR(128),
            translation TEXT,
            tag         VARCHAR(64)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dict_ecdict_lower ON dict_ecdict (word_lower)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_dict_ecdict_lower")
    op.execute("DROP TABLE IF EXISTS dict_ecdict")
