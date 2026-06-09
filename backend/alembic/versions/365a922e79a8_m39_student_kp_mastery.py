"""M39_student_kp_mastery

Revision ID: 365a922e79a8
Revises: 0025
Create Date: 2026-06-09 14:37:05.861144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '365a922e79a8'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_kp_mastery',
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('kp_key', sa.Text(), nullable=False),
        sa.Column('kp_id', sa.UUID(), nullable=True),
        sa.Column('correct_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('wrong_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_activity_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['kp_id'], ['knowledge_points.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('student_id', 'kp_key'),
    )


def downgrade() -> None:
    op.drop_table('student_kp_mastery')
