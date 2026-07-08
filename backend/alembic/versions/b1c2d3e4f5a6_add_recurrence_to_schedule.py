"""add recurrence fields to scheduled_meetings

Revision ID: b1c2d3e4f5a6
Revises: a9b1c2d3e4f5
Create Date: 2026-06-05 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a9b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scheduled_meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recurrence', sa.String(), nullable=False, server_default='none'))
        batch_op.add_column(sa.Column('recurrence_day', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('recurrence_time', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('timezone', sa.String(), nullable=False, server_default='Europe/Moscow'))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        # scheduled_at теперь nullable (для рекуррентных)
        batch_op.alter_column('scheduled_at', existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('scheduled_meetings', schema=None) as batch_op:
        batch_op.alter_column('scheduled_at', existing_type=sa.DateTime(), nullable=False)
        batch_op.drop_column('is_active')
        batch_op.drop_column('timezone')
        batch_op.drop_column('recurrence_time')
        batch_op.drop_column('recurrence_day')
        batch_op.drop_column('recurrence')
