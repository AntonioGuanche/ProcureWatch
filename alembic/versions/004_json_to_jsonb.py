"""Convert JSON columns to JSONB for DISTINCT compatibility.

PostgreSQL cannot compare JSON columns for equality, which breaks
SELECT DISTINCT queries. JSONB supports equality and is more performant.

Revision ID: 004
Revises: 003
Create Date: 2026-02-10
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

# All JSON columns in the notices table
JSON_COLUMNS = [
    "cpv_additional_codes",
    "nuts_codes",
    "organisation_names",
    "publication_languages",
    "raw_data",
    "keywords",
]


def upgrade() -> None:
    for col in JSON_COLUMNS:
        op.execute(
            f"ALTER TABLE notices ALTER COLUMN {col} TYPE jsonb USING {col}::jsonb"
        )


def downgrade() -> None:
    for col in JSON_COLUMNS:
        op.execute(
            f"ALTER TABLE notices ALTER COLUMN {col} TYPE json USING {col}::json"
        )
