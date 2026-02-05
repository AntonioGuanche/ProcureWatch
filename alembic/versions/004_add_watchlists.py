"""add watchlists

Revision ID: 004
Revises: 003
Create Date: 2026-01-28 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("term", sa.String(length=255), nullable=True),
        sa.Column("cpv_prefix", sa.String(length=20), nullable=True),
        sa.Column("buyer_contains", sa.String(length=255), nullable=True),
        sa.Column("procedure_type", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False, server_default="BE"),
        sa.Column("language", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("watchlists")
