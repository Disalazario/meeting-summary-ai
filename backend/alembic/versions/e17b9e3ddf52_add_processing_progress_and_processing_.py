"""add processing_progress and processing_eta_seconds to meetings

Revision ID: e17b9e3ddf52
Revises: 75f03792fccc
Create Date: 2026-04-03 11:12:24.580045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e17b9e3ddf52'
down_revision: Union[str, Sequence[str], None] = '75f03792fccc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('processing_progress', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('processing_eta_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('processing_eta_seconds')
        batch_op.drop_column('processing_progress')
