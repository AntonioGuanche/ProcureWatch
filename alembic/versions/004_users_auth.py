"""Add users table and user_id to watchlists.

Revision ID: 004
Revises: 003
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Add user_id to watchlists (nullable for existing data)
    op.add_column(
        "watchlists",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlists_user_id", "watchlists")
    op.drop_column("watchlists", "user_id")
    op.drop_table("users")
