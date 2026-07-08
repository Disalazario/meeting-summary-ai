"""add planfix cache tables

Revision ID: d5b2c3e4f6a7
Revises: c4a1b2d3e4f5
Create Date: 2026-05-18 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5b2c3e4f6a7'
down_revision: Union[str, Sequence[str], None] = 'c4a1b2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'planfix_users_cache',
        sa.Column('planfix_id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'planfix_projects_cache',
        sa.Column('planfix_id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'planfix_sync_state',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('user_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('project_count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('planfix_sync_state')
    op.drop_table('planfix_projects_cache')
    op.drop_table('planfix_users_cache')
