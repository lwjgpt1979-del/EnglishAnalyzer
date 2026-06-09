"""M39b_kp_mastery_sources_description

Revision ID: eea9918c4218
Revises: 365a922e79a8
Create Date: 2026-06-09 14:45:21.466506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eea9918c4218'
down_revision: Union[str, Sequence[str], None] = '365a922e79a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('student_kp_mastery', sa.Column(
        'sources', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False,
    ))
    op.add_column('student_kp_mastery', sa.Column('kp_description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('student_kp_mastery', 'kp_description')
    op.drop_column('student_kp_mastery', 'sources')
