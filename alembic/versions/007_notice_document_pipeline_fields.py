"""add notice_document pipeline fields (local_path, sha256, download/extraction status)

Revision ID: 007
Revises: 006
Create Date: 2026-01-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notice_documents", sa.Column("local_path", sa.String(length=2000), nullable=True))
    op.add_column("notice_documents", sa.Column("content_type", sa.String(length=100), nullable=True))
    op.add_column("notice_documents", sa.Column("file_size", sa.Integer(), nullable=True))
    op.add_column("notice_documents", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column("notice_documents", sa.Column("downloaded_at", sa.DateTime(), nullable=True))
    op.add_column("notice_documents", sa.Column("download_status", sa.String(length=20), nullable=True))
    op.add_column("notice_documents", sa.Column("download_error", sa.Text(), nullable=True))
    op.add_column("notice_documents", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column("notice_documents", sa.Column("extracted_at", sa.DateTime(), nullable=True))
    op.add_column("notice_documents", sa.Column("extraction_status", sa.String(length=20), nullable=True))
    op.add_column("notice_documents", sa.Column("extraction_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notice_documents", "extraction_error")
    op.drop_column("notice_documents", "extraction_status")
    op.drop_column("notice_documents", "extracted_at")
    op.drop_column("notice_documents", "extracted_text")
    op.drop_column("notice_documents", "download_error")
    op.drop_column("notice_documents", "download_status")
    op.drop_column("notice_documents", "downloaded_at")
    op.drop_column("notice_documents", "sha256")
    op.drop_column("notice_documents", "file_size")
    op.drop_column("notice_documents", "content_type")
    op.drop_column("notice_documents", "local_path")
