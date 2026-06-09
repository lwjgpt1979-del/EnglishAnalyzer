"""class_papers + class_paper_questions（V2 M28 教师出卷）

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    # 老师从平台仿真题库选题组成的班级试卷
    op.create_table(
        'class_papers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('class_id', UUID(as_uuid=True),
                  sa.ForeignKey('classes.id'), nullable=False),
        sa.Column('teacher_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('textbook_version', sa.String, nullable=True),
        sa.Column('grade', sa.String, nullable=True),
        sa.Column('semester', sa.String, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String, nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_class_papers_class', 'class_papers', ['class_id'])

    # 班级试卷题目明细（引用仿真题）
    op.create_table(
        'class_paper_questions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('class_paper_id', UUID(as_uuid=True),
                  sa.ForeignKey('class_papers.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('sim_question_id', UUID(as_uuid=True),
                  sa.ForeignKey('simulated_questions.id'), nullable=False),
        sa.Column('order_no', sa.SmallInteger, nullable=False,
                  server_default=sa.text('1')),
    )
    op.create_index('ix_cpq_paper', 'class_paper_questions', ['class_paper_id'])
    op.create_unique_constraint(
        'uq_cpq_paper_question', 'class_paper_questions',
        ['class_paper_id', 'sim_question_id'],
    )


def downgrade():
    op.drop_table('class_paper_questions')
    op.drop_index('ix_class_papers_class', 'class_papers')
    op.drop_table('class_papers')
