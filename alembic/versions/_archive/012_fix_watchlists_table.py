"""Fix missing watchlists table (recreate if not present).

Revision ID: 012
Revises: 011
Create Date: 2026-02-07 16:00:00.000000

Migration 010 recreates watchlist_matches with FK to watchlists.id but never recreates
watchlists itself. If the DB was created from 010 (or watchlists was dropped), the
watchlist_matches table would reference a missing table. This migration ensures
watchlists exists with the final schema from app/db/models/watchlist.py (004+005+009+efc6b1140aa4).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "watchlists" in insp.get_table_names():
        return
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("keywords", sa.String(length=1000), nullable=True),
        sa.Column("countries", sa.String(length=100), nullable=True),
        sa.Column("cpv_prefixes", sa.String(length=200), nullable=True),
        sa.Column("sources", sa.Text(), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Watchlists was created by 004; we only create it here when missing. No-op on downgrade
    # so we do not drop a table that may have been created by an earlier migration.
    pass
