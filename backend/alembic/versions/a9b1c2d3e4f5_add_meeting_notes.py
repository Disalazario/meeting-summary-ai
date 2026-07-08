"""add meeting_notes table

Revision ID: a9b1c2d3e4f5
Revises: f7a8b9c0d1e2
Create Date: 2026-06-05 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9b1c2d3e4f5'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("enriched_content", sa.Text(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_meeting_notes_meeting_user"),
    )
    op.create_index(
        "ix_meeting_notes_meeting_id", "meeting_notes", ["meeting_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_notes_meeting_id", table_name="meeting_notes")
    op.drop_table("meeting_notes")
