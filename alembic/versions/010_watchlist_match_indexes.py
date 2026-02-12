"""add indexes on watchlist_matches for performance

Revision ID: 010
Revises: 009
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"])
    op.create_index("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"])
    # Critical missing indexes on notices table for watchlist queries
    op.create_index("ix_notices_source", "notices", ["source"])
    op.create_index("ix_notices_created_at", "notices", ["created_at"])


def downgrade():
    op.drop_index("ix_notices_created_at", "notices")
    op.drop_index("ix_notices_source", "notices")
    op.drop_index("ix_watchlist_matches_notice_id", "watchlist_matches")
    op.drop_index("ix_watchlist_matches_watchlist_id", "watchlist_matches")
