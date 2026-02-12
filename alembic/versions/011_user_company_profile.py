"""add company profile fields to users

Revision ID: 011
Revises: 010
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "011"
down_revision: str = "010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def _index_exists(conn, name: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": name},
    ).fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()

    columns = [
        # Company identity
        ("company_name", sa.String(255), {}),
        ("vat_number", sa.String(20), {"comment": "VAT number, e.g. BE0123456789"}),
        ("nace_codes", sa.String(500), {"comment": "Comma-separated NACE codes (auto from BCE)"}),
        # Location
        ("address", sa.String(500), {}),
        ("postal_code", sa.String(10), {}),
        ("city", sa.String(100), {}),
        ("country", sa.String(5), {"server_default": "BE", "comment": "ISO 3166-1 alpha-2"}),
        ("latitude", sa.Float, {}),
        ("longitude", sa.Float, {}),
    ]

    for col_name, col_type, kwargs in columns:
        if not _col_exists(conn, "users", col_name):
            op.add_column("users", sa.Column(col_name, col_type, nullable=True, **kwargs))

    # Indexes
    if not _index_exists(conn, "ix_users_vat_number"):
        op.create_index("ix_users_vat_number", "users", ["vat_number"], unique=True)
    if not _index_exists(conn, "ix_users_country"):
        op.create_index("ix_users_country", "users", ["country"])


def downgrade() -> None:
    op.drop_index("ix_users_country", table_name="users")
    op.drop_index("ix_users_vat_number", table_name="users")
    for col in ["longitude", "latitude", "country", "city", "postal_code",
                "address", "nace_codes", "vat_number", "company_name"]:
        op.drop_column("users", col)
