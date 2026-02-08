"""Add search_vector tsvector column with GIN index for full-text search.

Revision ID: 002
Revises: 001
Create Date: 2026-02-08

PostgreSQL only. Adds:
- search_vector tsvector column on notices
- GIN index for fast full-text queries
- Trigger to auto-update search_vector on INSERT/UPDATE of title/description
- Backfills existing rows
"""
from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect != "postgresql":
        # SQLite: no tsvector support, search falls back to ILIKE
        return

    # 1. Add search_vector column
    op.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS search_vector tsvector")

    # 2. Create GIN index
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_notices_search_vector
        ON notices USING GIN (search_vector)
    """)

    # 3. Create trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION notices_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 4. Create trigger
    op.execute("""
        DROP TRIGGER IF EXISTS notices_search_vector_trigger ON notices;
        CREATE TRIGGER notices_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, description ON notices
        FOR EACH ROW EXECUTE FUNCTION notices_search_vector_update();
    """)

    # 5. Backfill existing rows
    op.execute("""
        UPDATE notices SET search_vector =
            setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B')
    """)

    # 6. Additional useful indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_notices_notice_type ON notices (notice_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notices_source ON notices (source)")


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect != "postgresql":
        return

    op.execute("DROP TRIGGER IF EXISTS notices_search_vector_trigger ON notices")
    op.execute("DROP FUNCTION IF EXISTS notices_search_vector_update()")
    op.execute("DROP INDEX IF EXISTS ix_notices_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_notices_notice_type")
    op.execute("DROP INDEX IF EXISTS ix_notices_source")
    op.execute("ALTER TABLE notices DROP COLUMN IF EXISTS search_vector")
