"""watchlist refresh and notify fields

Revision ID: 005
Revises: 004
Create Date: 2026-01-28 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("watchlists", sa.Column("last_refresh_at", sa.DateTime(), nullable=True))
    op.add_column("watchlists", sa.Column("last_refresh_status", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("notify_email", sa.String(length=255), nullable=True))
    op.add_column("watchlists", sa.Column("last_notified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlists", "last_notified_at")
    op.drop_column("watchlists", "notify_email")
    op.drop_column("watchlists", "last_refresh_status")
    op.drop_column("watchlists", "last_refresh_at")
