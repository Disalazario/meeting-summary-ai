"""add wiki RAG tables (wiki_pages + wiki_chunks)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-05 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wiki_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False, server_default="ru"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("wiki_updated_at", sa.DateTime(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "wiki_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["wiki_pages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_chunks_page_id", "wiki_chunks", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_wiki_chunks_page_id", table_name="wiki_chunks")
    op.drop_table("wiki_chunks")
    op.drop_table("wiki_pages")
