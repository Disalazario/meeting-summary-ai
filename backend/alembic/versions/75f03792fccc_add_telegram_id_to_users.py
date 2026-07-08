"""add telegram_id to users

Revision ID: 75f03792fccc
Revises: a1aef5ccef45
Create Date: 2026-02-25 14:39:53.969005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75f03792fccc'
down_revision: Union[str, Sequence[str], None] = 'a1aef5ccef45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('telegram_id', sa.String(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_telegram_id'), ['telegram_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_telegram_id'))
        batch_op.drop_column('telegram_id')
