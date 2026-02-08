"""add watchlist_matches table

Revision ID: 008
Revises: 007
Create Date: 2026-02-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("watchlist_id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("matched_on", sa.String(length=500), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "notice_id", name="uq_watchlist_match"),
    )
    op.create_index("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"])
    op.create_index("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_matches_notice_id", table_name="watchlist_matches")
    op.drop_index("ix_watchlist_matches_watchlist_id", table_name="watchlist_matches")
    op.drop_table("watchlist_matches")
