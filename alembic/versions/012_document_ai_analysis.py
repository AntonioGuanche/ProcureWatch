"""012 – add AI document analysis columns to notice_documents.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: str = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ai_analysis: cached Claude analysis of extracted PDF text
    # ai_analysis_generated_at: when the analysis was generated
    cols_to_add = [
        ("ai_analysis", sa.Text()),
        ("ai_analysis_generated_at", sa.DateTime()),
    ]

    if dialect == "postgresql":
        for col_name, col_type in cols_to_add:
            op.execute(
                f"ALTER TABLE notice_documents ADD COLUMN IF NOT EXISTS "
                f"{col_name} {'TEXT' if isinstance(col_type, sa.Text) else 'TIMESTAMP'}"
            )
    else:
        # SQLite: check existing columns
        inspector = sa.inspect(bind)
        existing = {c["name"] for c in inspector.get_columns("notice_documents")}
        for col_name, col_type in cols_to_add:
            if col_name not in existing:
                op.add_column("notice_documents", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    op.drop_column("notice_documents", "ai_analysis_generated_at")
    op.drop_column("notice_documents", "ai_analysis")
