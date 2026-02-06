"""update watchlist table for MVP: replace single fields with arrays

Revision ID: 009
Revises: 008
Create Date: 2026-02-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old columns
    op.drop_column("watchlists", "term")
    op.drop_column("watchlists", "cpv_prefix")
    op.drop_column("watchlists", "buyer_contains")
    op.drop_column("watchlists", "procedure_type")
    op.drop_column("watchlists", "country")
    op.drop_column("watchlists", "language")
    op.drop_column("watchlists", "is_enabled")
    op.drop_column("watchlists", "last_refresh_status")
    op.drop_column("watchlists", "notify_email")
    op.drop_column("watchlists", "last_notified_at")
    
    # Add new array columns (stored as comma-separated strings)
    op.add_column("watchlists", sa.Column("keywords", sa.String(length=1000), nullable=True))
    op.add_column("watchlists", sa.Column("countries", sa.String(length=100), nullable=True))
    op.add_column("watchlists", sa.Column("cpv_prefixes", sa.String(length=200), nullable=True))


def downgrade() -> None:
    # Restore old columns
    op.drop_column("watchlists", "cpv_prefixes")
    op.drop_column("watchlists", "countries")
    op.drop_column("watchlists", "keywords")
    
    op.add_column("watchlists", sa.Column("term", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("cpv_prefix", sa.String(length=20), nullable=True))
    op.add_column("watchlists", sa.Column("buyer_contains", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("procedure_type", sa.String(length=100), nullable=True))
    op.add_column("watchlists", sa.Column("country", sa.String(length=2), nullable=False, server_default="BE"))
    op.add_column("watchlists", sa.Column("language", sa.String(length=2), nullable=True))
    op.add_column("watchlists", sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("watchlists", sa.Column("last_refresh_status", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("notify_email", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("last_notified_at", sa.DateTime(), nullable=True))
