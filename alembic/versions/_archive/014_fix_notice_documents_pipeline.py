"""Fix notice_documents: add pipeline columns lost by migration 010.

Revision ID: 014
Revises: 013
Create Date: 2026-02-08 20:00:00.000000

Migration 010 dropped and recreated notice_documents WITHOUT the 11 pipeline
columns added by migration 007.  This migration adds them back (idempotent:
skips if columns already exist on SQLite/Postgres).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns that should exist on notice_documents per the NoticeDocument model
# but were lost when migration 010 dropped+recreated the table.
PIPELINE_COLUMNS: list[tuple[str, sa.types.TypeEngine]] = [
    ("local_path", sa.String(length=2000)),
    ("content_type", sa.String(length=100)),
    ("file_size", sa.Integer()),
    ("sha256", sa.String(length=64)),
    ("downloaded_at", sa.DateTime()),
    ("download_status", sa.String(length=20)),
    ("download_error", sa.Text()),
    ("extracted_text", sa.Text()),
    ("extracted_at", sa.DateTime()),
    ("extraction_status", sa.String(length=20)),
    ("extraction_error", sa.Text()),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = {col["name"] for col in insp.get_columns("notice_documents")}

    for col_name, col_type in PIPELINE_COLUMNS:
        if col_name not in existing:
            op.add_column(
                "notice_documents",
                sa.Column(col_name, col_type, nullable=True),
            )


def downgrade() -> None:
    for col_name, _ in reversed(PIPELINE_COLUMNS):
        op.drop_column("notice_documents", col_name)
