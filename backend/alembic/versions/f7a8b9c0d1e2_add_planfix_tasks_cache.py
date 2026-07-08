"""add planfix tasks cache + task-user link

Revision ID: f7a8b9c0d1e2
Revises: e6f3c7d8a9b1
Create Date: 2026-05-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f3c7d8a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'planfix_tasks_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('start_date', sa.String(), nullable=True),
        sa.Column('end_date', sa.String(), nullable=True),
        sa.Column('status_name', sa.String(), nullable=False, server_default=''),
        sa.Column('status_color', sa.String(), nullable=False, server_default='#888'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('project_name', sa.String(), nullable=True),
        sa.Column('assignees_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('assigner_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_planfix_tasks_cache_start_date', 'planfix_tasks_cache', ['start_date'])
    op.create_index('ix_planfix_tasks_cache_is_active', 'planfix_tasks_cache', ['is_active'])
    op.create_index('ix_planfix_tasks_cache_project_id', 'planfix_tasks_cache', ['project_id'])

    op.create_table(
        'planfix_task_users',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['planfix_tasks_cache.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('task_id', 'user_id', 'role'),
    )
    op.create_index('ix_planfix_task_users_user_id', 'planfix_task_users', ['user_id'])

    # Добавить task_count в sync_state
    with op.batch_alter_table('planfix_sync_state', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('planfix_sync_state', schema=None) as batch_op:
        batch_op.drop_column('task_count')
    op.drop_index('ix_planfix_task_users_user_id', table_name='planfix_task_users')
    op.drop_table('planfix_task_users')
    op.drop_index('ix_planfix_tasks_cache_project_id', table_name='planfix_tasks_cache')
    op.drop_index('ix_planfix_tasks_cache_is_active', table_name='planfix_tasks_cache')
    op.drop_index('ix_planfix_tasks_cache_start_date', table_name='planfix_tasks_cache')
    op.drop_table('planfix_tasks_cache')
