"""Add user_favorites table.

Revision ID: 005
Revises: 004
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("notice_id", sa.String(36), sa.ForeignKey("notices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "notice_id", name="uq_user_favorite"),
    )


def downgrade() -> None:
    op.drop_table("user_favorites")
