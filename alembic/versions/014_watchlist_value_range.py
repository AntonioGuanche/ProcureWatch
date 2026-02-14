"""Add value_min and value_max to watchlists for price range filtering.

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlists", sa.Column("value_min", sa.Float(), nullable=True))
    op.add_column("watchlists", sa.Column("value_max", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlists", "value_max")
    op.drop_column("watchlists", "value_min")
