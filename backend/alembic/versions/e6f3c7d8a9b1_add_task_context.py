"""add tasks.context column

Revision ID: e6f3c7d8a9b1
Revises: d5b2c3e4f6a7
Create Date: 2026-05-18 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f3c7d8a9b1'
down_revision: Union[str, Sequence[str], None] = 'd5b2c3e4f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('context', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('context')
