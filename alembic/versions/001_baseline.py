"""Squashed baseline: full schema for ProcureWatch.

Revision ID: 001
Revises: (none)
Create Date: 2026-02-08 20:30:00.000000

This single migration creates every table from scratch, matching the current
SQLAlchemy models exactly.  It replaces the original migrations 001-014.

For EXISTING production databases already at revision 013 or 014:
    1. Run 014 first if not done:  alembic upgrade 014
    2. Then stamp:                 alembic stamp 001

For FRESH databases:
    alembic upgrade head
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── filters ──────────────────────────────────────────────────────────
    op.create_table(
        "filters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("keywords", sa.String(length=500), nullable=True),
        sa.Column("cpv_prefixes", sa.String(length=200), nullable=True),
        sa.Column("countries", sa.String(length=100), nullable=True),
        sa.Column("buyer_keywords", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── notices (ProcurementNotice) ──────────────────────────────────────
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
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("agreement_status", sa.String(length=100), nullable=True),
        sa.Column("dossier_status", sa.String(length=100), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("required_accreditation", sa.String(length=500), nullable=True),
        sa.Column("dossier_number", sa.String(length=255), nullable=True),
        sa.Column("dossier_title", sa.Text(), nullable=True),
        sa.Column("agreement_id", sa.String(length=255), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("migrated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_notices_source_id"),
    )
    op.create_index("ix_notices_source_id", "notices", ["source_id"])
    op.create_index("ix_notices_publication_workspace_id", "notices", ["publication_workspace_id"])
    op.create_index("ix_notices_cpv_main_code", "notices", ["cpv_main_code"])
    op.create_index("ix_notices_publication_date", "notices", ["publication_date"])
    op.create_index("ix_notices_title", "notices", ["title"])
    op.create_index("ix_notices_deadline", "notices", ["deadline"])

    # ── watchlists ───────────────────────────────────────────────────────
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("keywords", sa.String(length=1000), nullable=True),
        sa.Column("countries", sa.String(length=100), nullable=True),
        sa.Column("cpv_prefixes", sa.String(length=200), nullable=True),
        sa.Column("sources", sa.Text(), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── import_runs ──────────────────────────────────────────────────────
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

    # ── notice_details (FK → notices) ────────────────────────────────────
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

    # ── notice_lots (FK → notices) ───────────────────────────────────────
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

    # ── notice_documents (FK → notices, notice_lots) ─────────────────────
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
        # Pipeline: download
        sa.Column("local_path", sa.String(length=2000), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("download_status", sa.String(length=20), nullable=True),
        sa.Column("download_error", sa.Text(), nullable=True),
        # Pipeline: text extraction
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
        sa.Column("extraction_status", sa.String(length=20), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_id"], ["notice_lots.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notice_documents_notice_id", "notice_documents", ["notice_id"])
    op.create_index("ix_notice_documents_lot_id", "notice_documents", ["lot_id"])

    # ── notice_cpv_additional (FK → notices) ─────────────────────────────
    op.create_table(
        "notice_cpv_additional",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("cpv_code", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notice_cpv_additional_notice_id", "notice_cpv_additional", ["notice_id"])

    # ── watchlist_matches (FK → notices, watchlists) ─────────────────────
    op.create_table(
        "watchlist_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("watchlist_id", sa.String(length=36), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("matched_on", sa.String(length=500), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("watchlist_id", "notice_id", name="uq_watchlist_match"),
    )
    op.create_index("ix_watchlist_matches_watchlist_id", "watchlist_matches", ["watchlist_id"])
    op.create_index("ix_watchlist_matches_notice_id", "watchlist_matches", ["notice_id"])


def downgrade() -> None:
    op.drop_table("watchlist_matches")
    op.drop_table("notice_cpv_additional")
    op.drop_table("notice_documents")
    op.drop_table("notice_lots")
    op.drop_table("notice_details")
    op.drop_table("import_runs")
    op.drop_table("watchlists")
    op.drop_table("notices")
    op.drop_table("filters")
