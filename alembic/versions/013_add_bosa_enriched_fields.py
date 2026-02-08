"""Add BOSA enriched fields to notices.

Revision ID: 013
Revises: 012
Create Date: 2026-02-07 18:00:00.000000

Adds url, status, agreement_status, dossier_status, cancelled_at, required_accreditation,
dossier_number, dossier_title, agreement_id, keywords, migrated to notices table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notices", sa.Column("url", sa.String(length=1000), nullable=True))
    op.add_column("notices", sa.Column("status", sa.String(length=50), nullable=True))
    op.add_column("notices", sa.Column("agreement_status", sa.String(length=100), nullable=True))
    op.add_column("notices", sa.Column("dossier_status", sa.String(length=100), nullable=True))
    op.add_column("notices", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("notices", sa.Column("required_accreditation", sa.String(length=500), nullable=True))
    op.add_column("notices", sa.Column("dossier_number", sa.String(length=255), nullable=True))
    op.add_column("notices", sa.Column("dossier_title", sa.Text(), nullable=True))
    op.add_column("notices", sa.Column("agreement_id", sa.String(length=255), nullable=True))
    op.add_column("notices", sa.Column("keywords", sa.JSON(), nullable=True))
    op.add_column("notices", sa.Column("migrated", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("notices", "migrated")
    op.drop_column("notices", "keywords")
    op.drop_column("notices", "agreement_id")
    op.drop_column("notices", "dossier_title")
    op.drop_column("notices", "dossier_number")
    op.drop_column("notices", "required_accreditation")
    op.drop_column("notices", "cancelled_at")
    op.drop_column("notices", "dossier_status")
    op.drop_column("notices", "agreement_status")
    op.drop_column("notices", "status")
    op.drop_column("notices", "url")
