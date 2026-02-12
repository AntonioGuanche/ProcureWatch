"""add index on procedure_id for CAN-CN linking

Revision ID: 009
Revises: 008
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_procurement_notices_procedure_id", "procurement_notices", ["procedure_id"])


def downgrade() -> None:
    op.drop_index("ix_procurement_notices_procedure_id", "procurement_notices")
