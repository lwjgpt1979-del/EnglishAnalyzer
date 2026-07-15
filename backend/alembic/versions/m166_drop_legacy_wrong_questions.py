"""下线旧「拍照单题」错题体系:DROP wrong_questions + ai_analyses + ocr_tasks + teacher_comments。

错题已统一到 wrong_record(统一错题中枢)。拍照单题上传/OCR/AI 逐题诊断/教师错题批注 一并退休。
不可逆(down 仅重建空表骨架,不恢复数据)。

Revision ID: m166_drop_legacy_wrong_questions
Revises: m165_wrong_record_source_id
Create Date: 2026-07-15
"""
from alembic import op

revision = "m166_drop_legacy_wrong_questions"
down_revision = "m165_wrong_record_source_id"
branch_labels = None
depends_on = None

def upgrade():
    for t in ("ai_analyses", "ocr_tasks", "teacher_comments", "wrong_questions"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

def downgrade():
    # 旧体系已退休,不恢复;如需回滚请从备份还原。留空以免误重建残表。
    pass
