"""add index on procedure_id for CAN-CN linking

Revision ID: 009
Revises: 008
"""
from alembic import op
from sqlalchemy import text

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if index already exists (idempotent)
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_notices_procedure_id'"
    )).fetchone()

    if not result:
        op.create_index(
            "ix_notices_procedure_id",
            "notices",
            ["procedure_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_notices_procedure_id", "notices")
