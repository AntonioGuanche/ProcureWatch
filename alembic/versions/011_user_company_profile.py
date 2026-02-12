"""add company profile fields to users

Revision ID: 011
Revises: 010
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str = "010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Company identity
    op.add_column("users", sa.Column("company_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("vat_number", sa.String(20), nullable=True,
                                      comment="VAT number, e.g. BE0123456789"))
    op.add_column("users", sa.Column("nace_codes", sa.String(500), nullable=True,
                                      comment="Comma-separated NACE codes (auto from BCE)"))

    # Location
    op.add_column("users", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("postal_code", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(5), nullable=True,
                                      server_default="BE", comment="ISO 3166-1 alpha-2"))
    op.add_column("users", sa.Column("latitude", sa.Float, nullable=True))
    op.add_column("users", sa.Column("longitude", sa.Float, nullable=True))

    # Useful indexes
    op.create_index("ix_users_vat_number", "users", ["vat_number"], unique=True)
    op.create_index("ix_users_country", "users", ["country"])


def downgrade() -> None:
    op.drop_index("ix_users_country", table_name="users")
    op.drop_index("ix_users_vat_number", table_name="users")
    for col in ["longitude", "latitude", "country", "city", "postal_code",
                "address", "nace_codes", "vat_number", "company_name"]:
        op.drop_column("users", col)
