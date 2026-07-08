"""add voice_profiles table for speaker recognition

Revision ID: c4a1b2d3e4f5
Revises: e17b9e3ddf52
Create Date: 2026-05-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a1b2d3e4f5'
down_revision: Union[str, Sequence[str], None] = 'e17b9e3ddf52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'voice_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.LargeBinary(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_voice_profiles_user_id'),
    )
    op.create_index('ix_voice_profiles_user_id', 'voice_profiles', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_voice_profiles_user_id', table_name='voice_profiles')
    op.drop_table('voice_profiles')
