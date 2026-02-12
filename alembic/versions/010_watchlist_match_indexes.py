"""add indexes on watchlist_matches for performance

Revision ID: 010
Revises: 009
"""
from alembic import op
from sqlalchemy import text

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def _index_exists(conn, name: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": name},
    ).fetchone() is not None


def upgrade():
    conn = op.get_bind()

    indexes = [
        ("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"]),
        ("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"]),
        ("ix_notices_source", "notices", ["source"]),
        ("ix_notices_created_at", "notices", ["created_at"]),
    ]

    for name, table, columns in indexes:
        if not _index_exists(conn, name):
            op.create_index(name, table, columns)


def downgrade():
    op.drop_index("ix_notices_created_at", "notices")
    op.drop_index("ix_notices_source", "notices")
    op.drop_index("ix_watchlist_matches_notice_id", "watchlist_matches")
    op.drop_index("ix_watchlist_matches_watchlist_id", "watchlist_matches")
