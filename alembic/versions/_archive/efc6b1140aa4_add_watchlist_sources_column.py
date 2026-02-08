"""add watchlist sources column

Revision ID: efc6b1140aa4
Revises: 009
Create Date: 2026-02-05 17:01:20.553715

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efc6b1140aa4'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sources column (nullable initially for safe migration)
    op.add_column("watchlists", sa.Column("sources", sa.Text(), nullable=True))
    
    # Backfill: set default ["TED", "BOSA"] for all existing rows
    default_sources_json = json.dumps(["TED", "BOSA"])
    op.execute(
        sa.text("UPDATE watchlists SET sources = :default_sources WHERE sources IS NULL").bindparams(
            default_sources=default_sources_json
        )
    )


def downgrade() -> None:
    op.drop_column("watchlists", "sources")
