"""scheduled_meetings: add meeting_url column

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-29 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scheduled_meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('meeting_url', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scheduled_meetings', schema=None) as batch_op:
        batch_op.drop_column('meeting_url')
