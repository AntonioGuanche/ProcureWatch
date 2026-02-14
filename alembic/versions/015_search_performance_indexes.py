"""Add performance indexes for search filters and sorting.

Missing indexes on frequently filtered/sorted columns:
- estimated_value: value range filters + value sort
- award_value: award sort
- Composite (source, publication_date): default search pattern
- Partial (deadline) WHERE NOT NULL: active-only filter
- GIN on nuts_codes: NUTS prefix filter
- Expression CPV division: facet grouping

Revision ID: 015
Revises: 014
"""
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Value columns (filters + sort, partial — only non-null rows)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_estimated_value "
        "ON notices (estimated_value) WHERE estimated_value IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_award_value "
        "ON notices (award_value) WHERE award_value IS NOT NULL"
    )

    # Composite: most common default browse (source filter + date sort)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_source_pubdate "
        "ON notices (source, publication_date DESC NULLS LAST)"
    )

    # Partial: active-only queries (deadline > now)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_deadline_active "
        "ON notices (deadline ASC NULLS LAST) WHERE deadline IS NOT NULL"
    )

    # GIN on nuts_codes JSONB for array element search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_nuts_codes_gin "
        "ON notices USING GIN (nuts_codes jsonb_path_ops) "
        "WHERE nuts_codes IS NOT NULL"
    )

    # Expression index: CPV 2-digit division for facet GROUP BY
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notices_cpv_division "
        "ON notices (LEFT(REPLACE(cpv_main_code, '-', ''), 2)) "
        "WHERE cpv_main_code IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notices_cpv_division")
    op.execute("DROP INDEX IF EXISTS ix_notices_nuts_codes_gin")
    op.execute("DROP INDEX IF EXISTS ix_notices_deadline_active")
    op.execute("DROP INDEX IF EXISTS ix_notices_source_pubdate")
    op.execute("DROP INDEX IF EXISTS ix_notices_award_value")
    op.execute("DROP INDEX IF EXISTS ix_notices_estimated_value")
