"""013 — create translation_cache table

Revision ID: 013
Revises: 012
Create Date: 2026-02-14
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_cache",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("keyword_normalised", sa.String(200), nullable=False),
        sa.Column("keyword_original", sa.String(200), nullable=False),
        sa.Column("fr", sa.Text(), nullable=True),
        sa.Column("nl", sa.Text(), nullable=True),
        sa.Column("en", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_translation_cache_keyword", "translation_cache", ["keyword_normalised"], unique=True)


def downgrade() -> None:
    op.drop_table("translation_cache")
