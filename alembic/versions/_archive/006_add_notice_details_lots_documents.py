"""add notice_details, notice_lots, notice_documents

Revision ID: 006
Revises: 005
Create Date: 2026-02-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notice_details",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("raw_json", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("notice_id", name="uq_notice_details_notice_id"),
    )
    op.create_index("ix_notice_details_notice_id", "notice_details", ["notice_id"])

    op.create_table(
        "notice_lots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("lot_number", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cpv_code", sa.String(length=20), nullable=True),
        sa.Column("nuts_code", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notice_lots_notice_id", "notice_lots", ["notice_id"])

    op.create_table(
        "notice_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("lot_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("checksum", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_id"], ["notice_lots.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notice_documents_notice_id", "notice_documents", ["notice_id"])
    op.create_index("ix_notice_documents_lot_id", "notice_documents", ["lot_id"])


def downgrade() -> None:
    op.drop_index("ix_notice_documents_lot_id", table_name="notice_documents")
    op.drop_index("ix_notice_documents_notice_id", table_name="notice_documents")
    op.drop_table("notice_documents")
    op.drop_index("ix_notice_lots_notice_id", table_name="notice_lots")
    op.drop_table("notice_lots")
    op.drop_index("ix_notice_details_notice_id", table_name="notice_details")
    op.drop_table("notice_details")
