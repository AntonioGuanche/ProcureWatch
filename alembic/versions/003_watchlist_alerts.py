"""Add enabled, notify_email, nuts_prefixes to watchlists.

Revision ID: 003
Revises: 002
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlists", sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("watchlists", sa.Column("notify_email", sa.String(255), nullable=True))
    op.add_column("watchlists", sa.Column("nuts_prefixes", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlists", "nuts_prefixes")
    op.drop_column("watchlists", "notify_email")
    op.drop_column("watchlists", "enabled")
