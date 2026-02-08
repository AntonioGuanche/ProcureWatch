"""Add import_runs table for daily import stats

Revision ID: 011
Revises: 010
Create Date: 2026-02-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("search_criteria_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_runs_source", "import_runs", ["source"])
    op.create_index("ix_import_runs_started_at", "import_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_import_runs_started_at", table_name="import_runs")
    op.drop_index("ix_import_runs_source", table_name="import_runs")
    op.drop_table("import_runs")
