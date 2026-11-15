"""feat: student portfolio share token + ability warnings support

Revision ID: c7a2f81e9d40
Revises: af9df446d338
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a2f81e9d40'
down_revision: Union[str, None] = 'af9df446d338'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('student_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portfolio_token', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_student_profiles_portfolio_token'), ['portfolio_token'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('student_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_student_profiles_portfolio_token'))
        batch_op.drop_column('portfolio_token')
