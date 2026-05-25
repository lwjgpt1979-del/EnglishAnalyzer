"""add_fk_indexes

Revision ID: 3c7d8e2f1a04
Revises: 9f9152b49be9
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3c7d8e2f1a04'
down_revision: Union[str, Sequence[str], None] = '9f9152b49be9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_wrong_questions_student_id', 'wrong_questions', ['student_id'])
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_memberships_user_id', 'memberships', ['user_id'])
    op.create_index('ix_ai_analyses_wrong_question_id', 'ai_analyses', ['wrong_question_id'])
    op.create_index('ix_practice_records_student_id', 'practice_records', ['student_id'])
    op.create_index('ix_assignment_submissions_student_id', 'assignment_submissions', ['student_id'])
    op.create_index('ix_ocr_tasks_wrong_question_id', 'ocr_tasks', ['wrong_question_id'])


def downgrade() -> None:
    op.drop_index('ix_ocr_tasks_wrong_question_id', table_name='ocr_tasks')
    op.drop_index('ix_assignment_submissions_student_id', table_name='assignment_submissions')
    op.drop_index('ix_practice_records_student_id', table_name='practice_records')
    op.drop_index('ix_ai_analyses_wrong_question_id', table_name='ai_analyses')
    op.drop_index('ix_memberships_user_id', table_name='memberships')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_index('ix_wrong_questions_student_id', table_name='wrong_questions')
