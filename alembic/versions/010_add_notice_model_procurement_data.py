"""Add notice model for procurement data

Revision ID: 010
Revises: efc6b1140aa4
Create Date: 2026-02-05 18:00:00.000000

Replaces the notices table with the Belgian procurement notice schema (ProcurementNotice).
Dependent tables (notice_details, notice_lots, notice_documents, notice_cpv_additional,
watchlist_matches) are dropped and recreated so FKs point to the new notices table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "efc6b1140aa4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop tables that reference notices (order: FKs first). Use IF EXISTS for portability.
    conn = op.get_bind()
    for table in ("notice_documents", "notice_lots", "notice_details", "notice_cpv_additional", "watchlist_matches", "notices"):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))

    # Create notices table (ProcurementNotice schema)
    op.create_table(
        "notices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("publication_workspace_id", sa.String(length=255), nullable=False),
        sa.Column("procedure_id", sa.String(length=255), nullable=True),
        sa.Column("dossier_id", sa.String(length=255), nullable=True),
        sa.Column("reference_number", sa.String(length=255), nullable=True),
        sa.Column("cpv_main_code", sa.String(length=20), nullable=True),
        sa.Column("cpv_additional_codes", sa.JSON(), nullable=True),
        sa.Column("nuts_codes", sa.JSON(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("insertion_date", sa.DateTime(), nullable=True),
        sa.Column("notice_type", sa.String(length=100), nullable=True),
        sa.Column("notice_sub_type", sa.String(length=100), nullable=True),
        sa.Column("form_type", sa.String(length=100), nullable=True),
        sa.Column("organisation_id", sa.String(length=255), nullable=True),
        sa.Column("organisation_names", sa.JSON(), nullable=True),
        sa.Column("publication_languages", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("estimated_value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_notices_source_id"),
    )
    op.create_index("ix_notices_source_id", "notices", ["source_id"])
    op.create_index("ix_notices_publication_workspace_id", "notices", ["publication_workspace_id"])
    op.create_index("ix_notices_cpv_main_code", "notices", ["cpv_main_code"])
    op.create_index("ix_notices_publication_date", "notices", ["publication_date"])
    op.create_index("ix_notices_deadline", "notices", ["deadline"])
    op.create_index("ix_notices_title", "notices", ["title"])

    # Recreate dependent tables
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

    op.create_table(
        "notice_cpv_additional",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("cpv_code", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notice_cpv_additional_notice_id", "notice_cpv_additional", ["notice_id"])

    op.create_table(
        "watchlist_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("watchlist_id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("matched_on", sa.String(length=500), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "notice_id", name="uq_watchlist_match"),
    )
    op.create_index("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"])
    op.create_index("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"])


def downgrade() -> None:
    # Drop dependent tables and new notices (SQLite drops indexes with table)
    op.drop_table("watchlist_matches")
    op.drop_table("notice_cpv_additional")
    op.drop_table("notice_documents")
    op.drop_table("notice_lots")
    op.drop_table("notice_details")
    op.drop_table("notices")

    # Recreate old notices table (schema from 002 + 003)
    op.create_table(
        "notices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("language", sa.String(length=2), nullable=True),
        sa.Column("cpv", sa.String(length=20), nullable=True),
        sa.Column("procedure_type", sa.String(length=100), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("raw_json", sa.String(), nullable=True),
        sa.Column("cpv_main_code", sa.String(length=20), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id", name="uq_notice_source_source_id"),
    )
    op.create_index("ix_notices_published_at", "notices", ["published_at"])
    op.create_index("ix_notices_deadline_at", "notices", ["deadline_at"])
    op.create_index("ix_notices_cpv", "notices", ["cpv"])
    op.create_index("ix_notices_cpv_main_code", "notices", ["cpv_main_code"])

    # Recreate dependent tables
    op.create_table(
        "watchlist_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("watchlist_id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("matched_on", sa.String(length=500), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "notice_id", name="uq_watchlist_match"),
    )
    op.create_index("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"])
    op.create_index("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"])

    op.create_table(
        "notice_cpv_additional",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("cpv_code", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notice_cpv_additional_notice_id", "notice_cpv_additional", ["notice_id"])

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
